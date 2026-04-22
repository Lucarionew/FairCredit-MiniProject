"""
pages/3_User_Apply.py — FairCredit 2.0
=======================================
User-facing loan application form.
ALL inputs are in human-friendly units:
  - Interest rates entered as % (e.g. 7 meaning 7%) → stored as 0.07 internally
  - Ratios entered as % (e.g. 42 meaning 42%)       → stored as 0.42 internally
  - Currency in ₹ (natural values)
  - Scores (Credit Score, Payment History %) as natural numbers

Conversion happens silently before saving — user never sees decimal ratios.

FIX LOG:
  1. min_value error — all ufield() defaults now match or exceed their min_val
  2. Auto-calculated fields — InterestRate, MonthlyEMI, EMIBurdenRatio, TotalDTI
     are computed from user inputs, not entered manually
  3. display_input keys now match exactly what Banker Queue reads
"""

import streamlit as st
import pandas as pd
import math

# ── Auth guard ─────────────────────────────────────────────────────────────────
if not st.session_state.get("logged_in"):
    st.warning("Please sign in from the Home page.")
    st.stop()
if st.session_state.get("role") != "user":
    st.error("This page is for applicants only. Bankers use the Decision Panel.")
    st.stop()

from firebase_config import submit_application

uid   = st.session_state["uid"]
email = st.session_state["email"]
name  = st.session_state["display_name"]

# ── Already submitted check ────────────────────────────────────────────────────
if st.session_state.get("application_submitted"):
    st.success("✅ Your application has already been submitted!")
    st.info("Go to **📬 My Application** in the sidebar to check your status.")
    if st.button("Submit another application"):
        st.session_state.pop("application_submitted", None)
        st.session_state.pop("last_submitted_app_id", None)
        st.rerun()
    st.stop()

# ── Page ───────────────────────────────────────────────────────────────────────
st.title("📝 Loan Application")
st.caption("All fields use standard units — enter values as you would write them naturally.")
st.divider()

# ── Helper: user-friendly number input ────────────────────────────────────────
def ufield(label, min_val=0.0, max_val=None, step=1.0, fmt="%.1f",
           help_text=None, key=None, default=None):
    """
    FIX 1: default now always >= min_val.
    If caller passes default=None, we set it to min_val automatically.
    """
    if default is None:
        default = min_val
    # Safety clamp: if provided default is below min, clamp up
    default = max(float(default), float(min_val))

    kwargs = dict(
        label=label, value=float(default),
        step=float(step), format=fmt,
        min_value=float(min_val),
        key=key,
    )
    if max_val is not None:
        kwargs["max_value"] = float(max_val)
    if help_text:
        kwargs["help"] = help_text
    return st.number_input(**kwargs)

def ucheckbox(label, key, default=False):
    return int(st.checkbox(label, value=default, key=key))

# ── EMI Calculator helper ──────────────────────────────────────────────────────
def calc_emi(principal: float, annual_rate_pct: float, months: int) -> float:
    """
    Standard reducing-balance EMI formula.
    Returns monthly EMI in ₹. Returns 0 if rate is 0.
    """
    if principal <= 0 or months <= 0:
        return 0.0
    if annual_rate_pct <= 0:
        return principal / months  # zero-interest: flat division
    r = (annual_rate_pct / 100.0) / 12.0  # monthly rate
    emi = principal * r * (1 + r) ** months / ((1 + r) ** months - 1)
    return round(emi, 2)

# ── FORM ───────────────────────────────────────────────────────────────────────
with st.form("user_application_form"):

    # ── Personal details ──────────────────────────────────────────────────────
    st.subheader("👤 Personal Details")
    p1, p2 = st.columns(2)
    with p1:
        full_name = st.text_input("Full Name", value=name, key="u_fullname")
    with p2:
        phone = st.text_input("Phone Number", placeholder="e.g. 9876543210", key="u_phone")

    c1, c2, c3 = st.columns(3)
    with c1:
        # FIX 1: default=30 >= min_val=18 ✓
        age        = ufield("Age (years)", 18, 85, 1, "%.0f", key="u_age", default=30)
    with c2:
        # FIX 1: default=0 >= min_val=0 ✓
        dependents = ufield("Number of Dependents", 0, 10, 1, "%.0f", key="u_dep", default=0)
    with c3:
        experience = ufield("Work Experience (years)", 0, 50, 1, "%.0f", key="u_exp", default=5)

    c4, c5 = st.columns(2)
    with c4:
        job_tenure = ufield("Job Tenure at Current Employer (years)", 0, 50, 1, "%.0f",
                            help_text="How many years at your current job?",
                            key="u_tenure", default=2)
    with c5:
        emp_status = st.selectbox("Employment Status", ["Employed", "Self-Employed", "Unemployed"],
                                  key="u_empstatus")
        emp_self  = int(emp_status == "Self-Employed")
        emp_unemp = int(emp_status == "Unemployed")

    edu_level = st.selectbox("Education Level",
                             ["High School", "Bachelor", "Master", "Doctorate", "Other"],
                             key="u_edu")
    edu_bach = int(edu_level == "Bachelor")
    edu_doc  = int(edu_level == "Doctorate")
    edu_hs   = int(edu_level == "High School")
    edu_mast = int(edu_level == "Master")

    col_m, col_h = st.columns(2)
    with col_m:
        marital = st.selectbox("Marital Status", ["Single", "Married", "Widowed", "Divorced"],
                               key="u_marital")
        mar_marr = int(marital == "Married")
        mar_sing = int(marital == "Single")
        mar_wid  = int(marital == "Widowed")
    with col_h:
        home_status = st.selectbox("Home Ownership", ["Rent", "Own", "Other"],
                                   key="u_home")
        home_own  = int(home_status == "Own")
        home_rent = int(home_status == "Rent")
        home_oth  = int(home_status == "Other")

    st.divider()

    # ── Financial profile ─────────────────────────────────────────────────────
    st.subheader("💰 Financial Profile")
    st.caption("Enter your real financial figures. All amounts in Indian Rupees (₹).")

    fi1, fi2, fi3 = st.columns(3)
    with fi1:
        annual_inc  = ufield("Annual Income (₹)", 0, step=10000, fmt="%.0f",
                             help_text="Your total annual income before tax",
                             key="u_anninc", default=500000)
    with fi2:
        monthly_inc = ufield("Monthly Income (₹)", 0, step=1000, fmt="%.0f",
                             help_text="Your take-home monthly income",
                             key="u_moninc", default=41666)
    with fi3:
        credit_score = ufield("Credit Score", 300, 900, 1, "%.0f",
                              help_text="Your CIBIL / credit score (300–900)",
                              key="u_cscore", default=700)

    fi4, fi5, fi6 = st.columns(3)
    with fi4:
        monthly_debt = ufield("Monthly Debt Payments (₹)", 0, step=500, fmt="%.0f",
                              help_text="Total of all existing EMIs / loan payments per month",
                              key="u_mdebt", default=5000)
    with fi5:
        cc_util_pct  = ufield("Credit Card Usage (%)", 0, 100, 1, "%.0f",
                              help_text="What % of your credit card limit do you typically use? (0–100)",
                              key="u_ccutil", default=30)
    with fi6:
        open_lines   = ufield("Number of Open Credit Accounts", 0, step=1, fmt="%.0f",
                              key="u_openlines", default=2)

    fi7, fi8 = st.columns(2)
    with fi7:
        inquiries    = ufield("Credit Inquiries in Last 6 Months", 0, step=1, fmt="%.0f",
                              help_text="How many times lenders have checked your credit recently",
                              key="u_inq", default=1)
    with fi8:
        dti_pct      = ufield("Debt-to-Income Ratio (%)", 0, 150, 1, "%.0f",
                              help_text="(Total monthly debt ÷ Monthly income) × 100. "
                                        "Example: if monthly debt = ₹10,000 and income = ₹40,000, enter 25",
                              key="u_dti", default=30)

    fi10, fi11, fi12 = st.columns(3)
    with fi10:
        pay_hist_pct  = ufield("Payment History Score (%)", 0, 100, 1, "%.0f",
                               help_text="How consistently you've paid bills on time (0–100%)",
                               key="u_payhist", default=85)
    with fi11:
        util_hist_pct = ufield("Utility Bills Paid on Time (%)", 0, 100, 1, "%.0f",
                               help_text="% of utility bills paid on time historically",
                               key="u_utilhist", default=90)
    with fi12:
        credit_hist   = ufield("Credit History Length (years)", 0, step=1, fmt="%.0f",
                               key="u_chist", default=5)

    fi13, fi14, fi15 = st.columns(3)
    with fi13:
        savings       = ufield("Savings Account Balance (₹)", 0, step=1000, fmt="%.0f",
                               key="u_savings", default=50000)
    with fi14:
        checking      = ufield("Checking Account Balance (₹)", 0, step=500, fmt="%.0f",
                               key="u_checking", default=20000)
    with fi15:
        net_worth     = ufield("Net Worth (₹)", min_val=-10_000_000, step=10000, fmt="%.0f",
                               help_text="Total Assets minus Total Liabilities",
                               key="u_networth", default=200000)

    fi16, fi17 = st.columns(2)
    with fi16:
        total_assets = ufield("Total Assets (₹)", 0, step=10000, fmt="%.0f",
                              key="u_tassets", default=500000)
    with fi17:
        total_liab   = ufield("Total Liabilities (₹)", 0, step=10000, fmt="%.0f",
                              key="u_tliab", default=300000)

    st.markdown("**Flags**")
    fl1, fl2, fl3 = st.columns(3)
    with fl1: bankrupt   = ucheckbox("Have you ever declared bankruptcy?", "u_bankrupt")
    with fl2: prev_def   = ufield("Previous Loan Defaults", 0, step=1, fmt="%.0f",
                                  key="u_prevdef", default=0)
    with fl3: missed_flag = ucheckbox("Have you missed any payments recently?", "u_missed")

    st.divider()

    # ── Loan details ──────────────────────────────────────────────────────────
    st.subheader("🏦 Loan Request")
    st.caption(
        "💡 The interest rate and EMI are automatically calculated by the system "
        "based on your profile and the loan details you enter."
    )

    la1, la2 = st.columns(2)
    with la1:
        loan_amt   = ufield("Loan Amount Requested (₹)", 0, step=10000, fmt="%.0f",
                            key="u_loanamt", default=500000)
    with la2:
        loan_dur   = ufield("Loan Duration (months)", 6, 360, 6, "%.0f",
                            help_text="How many months to repay",
                            key="u_loandur", default=36)

    loan_purpose = st.selectbox("Loan Purpose",
                                ["Home", "Education", "Debt Consolidation", "Other"],
                                key="u_loanpurpose")
    lp_home = int(loan_purpose == "Home")
    lp_edu  = int(loan_purpose == "Education")
    lp_debt = int(loan_purpose == "Debt Consolidation")
    lp_oth  = int(loan_purpose == "Other")

    # ── FIX 2: Auto-calculated loan fields ───────────────────────────────────
    # Base rate (bank's base lending rate, fixed by bank policy)
    BASE_RATE_PCT = 7.0  # 7% per annum — bank's standard base rate

    st.divider()
    st.markdown("#### 🔢 Calculated Loan Terms")
    st.caption("These values are computed automatically from your inputs.")

    st.divider()
    st.caption("By submitting, you confirm all information provided is accurate.")
    user_submitted = st.form_submit_button(
        "📤 Submit Application", use_container_width=True, type="primary"
    )

# ── On Submit: compute auto fields → convert units → save to Firestore ─────────
if user_submitted:

    # ── FIX 2: Compute interest rate from credit score ────────────────────────
    # Simple risk-based pricing: better credit score = lower spread over base
    # Spread ranges from 1% (excellent, 800+) to 12% (poor, <500)
    def _credit_spread(score: float) -> float:
        """Returns additional spread over base rate based on credit score."""
        if score >= 800:   return 1.0
        elif score >= 750: return 2.5
        elif score >= 700: return 4.0
        elif score >= 650: return 5.5
        elif score >= 600: return 7.0
        elif score >= 550: return 9.0
        elif score >= 500: return 11.0
        else:              return 12.0

    base_rate_pct = BASE_RATE_PCT
    spread_pct    = _credit_spread(credit_score)
    int_rate_pct  = base_rate_pct + spread_pct   # e.g. 7 + 5.5 = 12.5%

    # ── FIX 2: Compute monthly EMI using standard formula ────────────────────
    monthly_lp = calc_emi(loan_amt, int_rate_pct, int(loan_dur))

    # ── FIX 2: Compute EMI-to-income ratio ───────────────────────────────────
    if monthly_inc > 0:
        emi_ratio_pct = round((monthly_lp / monthly_inc) * 100, 1)
    else:
        emi_ratio_pct = 0.0

    # ── FIX 2: Compute Total DTI including new loan EMI ───────────────────────
    if monthly_inc > 0:
        total_dti_pct = round(((monthly_debt + monthly_lp) / monthly_inc) * 100, 1)
    else:
        total_dti_pct = 0.0

    # ── Unit conversions (% → decimal) ────────────────────────────────────────
    cc_util   = cc_util_pct   / 100.0   # 42% → 0.42
    dti       = dti_pct       / 100.0   # 30% → 0.30
    total_dti = total_dti_pct / 100.0
    pay_hist  = pay_hist_pct  / 100.0   # 85% → 0.85
    util_hist = util_hist_pct / 100.0
    base_rate = base_rate_pct / 100.0   # 7%  → 0.07
    int_rate  = int_rate_pct  / 100.0   # 12% → 0.12
    emi_ratio = emi_ratio_pct / 100.0

    # ── Derived features ───────────────────────────────────────────────────────
    high_util   = int(cc_util > 0.75)
    stl_ratio   = savings / (loan_amt + 1e-5)
    stl_ratio   = min(stl_ratio, 10.0)  # cap at 10 to avoid extreme values

    # ── Model-ready raw_input (47 features, all in model-expected units) ──────
    raw_input = {
        "Age":                              float(age),
        "AnnualIncome":                     float(annual_inc),
        "CreditScore":                      float(credit_score),
        "Experience":                       float(experience),
        "LoanAmount":                       float(loan_amt),
        "LoanDuration":                     float(loan_dur),
        "NumberOfDependents":               float(dependents),
        "MonthlyDebtPayments":              float(monthly_debt),
        "CreditCardUtilizationRate":        cc_util,
        "NumberOfOpenCreditLines":          float(open_lines),
        "NumberOfCreditInquiries":          float(inquiries),
        "DebtToIncomeRatio":                dti,
        "BankruptcyHistory":                float(bankrupt),
        "PreviousLoanDefaults":             float(prev_def),
        "PaymentHistory":                   pay_hist,
        "LengthOfCreditHistory":            float(credit_hist),
        "SavingsAccountBalance":            float(savings),
        "CheckingAccountBalance":           float(checking),
        "TotalAssets":                      float(total_assets),
        "TotalLiabilities":                 float(total_liab),
        "MonthlyIncome":                    float(monthly_inc),
        "UtilityBillsPaymentHistory":       util_hist,
        "JobTenure":                        float(job_tenure),
        "NetWorth":                         float(net_worth),
        "BaseInterestRate":                 base_rate,
        "InterestRate":                     int_rate,
        "MonthlyLoanPayment":               float(monthly_lp),
        "TotalDebtToIncomeRatio":           total_dti,
        "MissedPaymentFlag":                float(missed_flag),
        "HighUtilizationFlag":              float(high_util),
        "SavingsToLoanRatio":               stl_ratio,
        "EmploymentStatus_Self-Employed":   float(emp_self),
        "EmploymentStatus_Unemployed":      float(emp_unemp),
        "EducationLevel_Bachelor":          float(edu_bach),
        "EducationLevel_Doctorate":         float(edu_doc),
        "EducationLevel_High School":       float(edu_hs),
        "EducationLevel_Master":            float(edu_mast),
        "MaritalStatus_Married":            float(mar_marr),
        "MaritalStatus_Single":             float(mar_sing),
        "MaritalStatus_Widowed":            float(mar_wid),
        "HomeOwnershipStatus_Other":        float(home_oth),
        "HomeOwnershipStatus_Own":          float(home_own),
        "HomeOwnershipStatus_Rent":         float(home_rent),
        "LoanPurpose_Debt Consolidation":   float(lp_debt),
        "LoanPurpose_Education":            float(lp_edu),
        "LoanPurpose_Home":                 float(lp_home),
        "LoanPurpose_Other":                float(lp_oth),
    }

    # ── FIX 3: display_input keys match EXACTLY what Banker Queue reads ───────
    # Banker Queue looks for: LoanAmount, AnnualIncome, CreditScore,
    #                          DebtToIncomeRatio, PreviousLoanDefaults
    display_input = {
        # Personal
        "ApplicantName":         full_name,
        "Phone":                 phone,
        "Age":                   int(age),
        "EmploymentStatus":      emp_status,
        "EducationLevel":        edu_level,
        "MaritalStatus":         marital,
        "HomeOwnership":         home_status,
        "WorkExperience":        f"{int(experience)} years",
        "JobTenure":             f"{int(job_tenure)} years",
        "Dependents":            int(dependents),

        # Financial — keys match what 2_Banker_Queue.py dc1–dc5 read
        "AnnualIncome":          annual_inc,        # dc2 reads this
        "MonthlyIncome":         monthly_inc,
        "CreditScore":           int(credit_score), # dc3 reads this
        "MonthlyDebtPayments":   monthly_debt,
        "CreditCardUsage":       f"{int(cc_util_pct)}%",
        "DebtToIncomeRatio":     f"{dti_pct}%",     # dc4 reads this
        "TotalDTI":              f"{total_dti_pct}%",
        "PaymentHistory":        f"{int(pay_hist_pct)}%",
        "UtilityBillsOnTime":    f"{int(util_hist_pct)}%",
        "CreditHistoryLength":   f"{int(credit_hist)} years",
        "SavingsBalance":        savings,
        "CheckingBalance":       checking,
        "TotalAssets":           total_assets,
        "TotalLiabilities":      total_liab,
        "NetWorth":              net_worth,
        "PreviousLoanDefaults":  int(prev_def),     # dc5 reads this
        "BankruptcyHistory":     bool(bankrupt),
        "MissedPayments":        bool(missed_flag),

        # Loan — dc1 reads LoanAmount
        "LoanAmount":            loan_amt,           # dc1 reads this
        "LoanDuration":          f"{int(loan_dur)} months",
        "LoanPurpose":           loan_purpose,
        "BaseInterestRate":      f"{base_rate_pct}%",
        "InterestRate":          f"{int_rate_pct:.1f}%",   # auto-calculated
        "MonthlyEMI":            round(monthly_lp),         # auto-calculated
        "EMIBurdenRatio":        f"{emi_ratio_pct:.1f}%",   # auto-calculated
    }

    # ── Show auto-calculated summary before submitting ─────────────────────────
    st.info(
        f"**Auto-calculated loan terms:**  \n"
        f"- Interest Rate: **{int_rate_pct:.1f}%** per annum "
        f"(Base {base_rate_pct}% + {spread_pct}% credit risk spread)  \n"
        f"- Monthly EMI: **₹{round(monthly_lp):,}**  \n"
        f"- EMI as % of Income: **{emi_ratio_pct:.1f}%**  \n"
        f"- Total DTI (with new loan): **{total_dti_pct:.1f}%**"
    )

    with st.spinner("Submitting your application..."):
        try:
            app_id = submit_application(
                uid=uid,
                email=email,
                applicant_name=full_name,
                raw_input=raw_input,
                display_input=display_input,
            )
            st.session_state["application_submitted"]  = True
            st.session_state["last_submitted_app_id"]  = app_id
            st.success(f"✅ Application submitted successfully! Your Application ID: **{app_id[:12]}...**")
            st.info("A banker will review your application soon. Check **📬 My Application** for updates.")
            st.balloons()
        except Exception as e:
            st.error(f"Failed to submit application: {e}")