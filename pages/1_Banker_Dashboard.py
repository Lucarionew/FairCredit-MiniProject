"""
pages/1_Banker_Dashboard.py — FairCredit 2.0
=============================================
Banker Decision Panel.
Protected behind banker login.

FIX LOG:
  1. field() helper clamps default to min_val — fixes "value < min_value" crash
  2. Loan auto-calc fields (InterestRate, MonthlyLoanPayment, EMIBurdenRatio,
     TotalDebtToIncomeRatio) removed from manual form; computed after submit
  3. Queue tab: session state key is now written by this page too so navigation
     round-trip doesn't lose it; added st.rerun() guard
  4. _run_analysis() signature unchanged — queue path still passes all fields
"""

import streamlit as st
import pandas as pd
import joblib
import json
import os
from datetime import datetime

# ── Auth guard ─────────────────────────────────────────────────────────────────
if not st.session_state.get("logged_in"):
    st.warning("Please sign in from the Home page.")
    st.stop()
if st.session_state.get("role") != "banker":
    st.error("Access denied. This page is for bankers only.")
    st.stop()

from predict import predict_with_guard
from explain import explain
from firebase_config import get_application, update_banker_decision

# ── Load shared resources ──────────────────────────────────────────────────────
@st.cache_resource
def load_resources():
    scaler  = joblib.load("models/scaler.pkl")
    X_train = pd.read_csv("data/processed/X_train.csv")
    y_train = pd.read_csv("data/processed/y_train.csv").squeeze()
    return scaler, X_train, y_train

scaler, X_train, y_train = load_resources()

OVERRIDES_FILE = "overrides.csv"

def log_override(applicant_id, decision, note, risk_score):
    row = {
        "timestamp":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "applicant_id": applicant_id,
        "decision":     decision,
        "note":         note,
        "risk_score":   risk_score,
    }
    if os.path.exists(OVERRIDES_FILE):
        df = pd.read_csv(OVERRIDES_FILE)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_csv(OVERRIDES_FILE, index=False)

# ── EMI Calculator (mirrors 3_User_Apply.py) ──────────────────────────────────
def calc_emi(principal: float, annual_rate_pct: float, months: int) -> float:
    if principal <= 0 or months <= 0:
        return 0.0
    if annual_rate_pct <= 0:
        return principal / months
    r = (annual_rate_pct / 100.0) / 12.0
    emi = principal * r * (1 + r) ** months / ((1 + r) ** months - 1)
    return round(emi, 2)

def credit_spread(score: float) -> float:
    if score >= 800:   return 1.0
    elif score >= 750: return 2.5
    elif score >= 700: return 4.0
    elif score >= 650: return 5.5
    elif score >= 600: return 7.0
    elif score >= 550: return 9.0
    elif score >= 500: return 11.0
    else:              return 12.0

BASE_RATE_PCT = 7.0  # bank's standard base rate %

# ── Sample profiles ────────────────────────────────────────────────────────────
SAMPLES = {
    "Rahul Mehta — True Moderate (Yellow Tier)": {
        "Age": 34, "AnnualIncome": 58000, "CreditScore": 705,
        "Experience": 7, "LoanAmount": 22000, "LoanDuration": 36,
        "NumberOfDependents": 2, "MonthlyDebtPayments": 1600,
        "CreditCardUtilizationRate": 0.42, "NumberOfOpenCreditLines": 5,
        "NumberOfCreditInquiries": 3, "DebtToIncomeRatio": 0.36,
        "BankruptcyHistory": 0, "PreviousLoanDefaults": 0,
        "PaymentHistory": 0.78, "LengthOfCreditHistory": 6,
        "SavingsAccountBalance": 5000, "CheckingAccountBalance": 2000,
        "TotalAssets": 30000, "TotalLiabilities": 18000,
        "MonthlyIncome": 4833, "UtilityBillsPaymentHistory": 0.82,
        "JobTenure": 3, "NetWorth": 12000,
        "MissedPaymentFlag": 0, "HighUtilizationFlag": 1,
        "EmploymentStatus_Self-Employed": 0, "EmploymentStatus_Unemployed": 0,
        "EducationLevel_Bachelor": 1, "EducationLevel_Doctorate": 0,
        "EducationLevel_High School": 0, "EducationLevel_Master": 0,
        "MaritalStatus_Married": 1, "MaritalStatus_Single": 0, "MaritalStatus_Widowed": 0,
        "HomeOwnershipStatus_Other": 0, "HomeOwnershipStatus_Own": 0, "HomeOwnershipStatus_Rent": 1,
        "LoanPurpose_Debt Consolidation": 0, "LoanPurpose_Education": 0,
        "LoanPurpose_Home": 1, "LoanPurpose_Other": 0,
    },
    "Priya Sharma — Low Risk": {
        "Age": 42, "AnnualIncome": 145000, "CreditScore": 780,
        "Experience": 15, "LoanAmount": 30000, "LoanDuration": 24,
        "NumberOfDependents": 1, "MonthlyDebtPayments": 900,
        "CreditCardUtilizationRate": 0.12, "NumberOfOpenCreditLines": 5,
        "NumberOfCreditInquiries": 1, "DebtToIncomeRatio": 0.15,
        "BankruptcyHistory": 0, "PreviousLoanDefaults": 0,
        "PaymentHistory": 0.97, "LengthOfCreditHistory": 14,
        "SavingsAccountBalance": 28000, "CheckingAccountBalance": 8000,
        "TotalAssets": 180000, "TotalLiabilities": 30000,
        "MonthlyIncome": 12083, "UtilityBillsPaymentHistory": 0.95,
        "JobTenure": 12, "NetWorth": 150000,
        "MissedPaymentFlag": 0, "HighUtilizationFlag": 0,
        "EmploymentStatus_Self-Employed": 0, "EmploymentStatus_Unemployed": 0,
        "EducationLevel_Bachelor": 0, "EducationLevel_Doctorate": 0,
        "EducationLevel_High School": 0, "EducationLevel_Master": 1,
        "MaritalStatus_Married": 1, "MaritalStatus_Single": 0, "MaritalStatus_Widowed": 0,
        "HomeOwnershipStatus_Other": 0, "HomeOwnershipStatus_Own": 1, "HomeOwnershipStatus_Rent": 0,
        "LoanPurpose_Debt Consolidation": 0, "LoanPurpose_Education": 0,
        "LoanPurpose_Home": 0, "LoanPurpose_Other": 1,
    },
    "Arjun Verma — High Risk": {
        "Age": 27, "AnnualIncome": 19000, "CreditScore": 480,
        "Experience": 2, "LoanAmount": 12000, "LoanDuration": 60,
        "NumberOfDependents": 3, "MonthlyDebtPayments": 1400,
        "CreditCardUtilizationRate": 0.88, "NumberOfOpenCreditLines": 7,
        "NumberOfCreditInquiries": 8, "DebtToIncomeRatio": 0.88,
        "BankruptcyHistory": 0, "PreviousLoanDefaults": 3,
        "PaymentHistory": 0.41, "LengthOfCreditHistory": 2,
        "SavingsAccountBalance": 300, "CheckingAccountBalance": 150,
        "TotalAssets": 3000, "TotalLiabilities": 14000,
        "MonthlyIncome": 1583, "UtilityBillsPaymentHistory": 0.45,
        "JobTenure": 1, "NetWorth": -11000,
        "MissedPaymentFlag": 1, "HighUtilizationFlag": 1,
        "EmploymentStatus_Self-Employed": 1, "EmploymentStatus_Unemployed": 0,
        "EducationLevel_Bachelor": 0, "EducationLevel_Doctorate": 0,
        "EducationLevel_High School": 1, "EducationLevel_Master": 0,
        "MaritalStatus_Married": 0, "MaritalStatus_Single": 1, "MaritalStatus_Widowed": 0,
        "HomeOwnershipStatus_Other": 0, "HomeOwnershipStatus_Own": 0, "HomeOwnershipStatus_Rent": 1,
        "LoanPurpose_Debt Consolidation": 1, "LoanPurpose_Education": 0,
        "LoanPurpose_Home": 0, "LoanPurpose_Other": 0,
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS RUNNER
# ══════════════════════════════════════════════════════════════════════════════
def _run_analysis(
    applicant_id, age, dependents, experience, job_tenure,
    emp_self, emp_unemp, edu_bach, edu_doc, edu_hs, edu_mast,
    mar_marr, mar_sing, mar_wid, home_own, home_rent, home_oth,
    annual_inc, monthly_inc, credit_score, monthly_debt, cc_util,
    open_lines, inquiries, dti, total_dti, pay_hist, util_hist,
    credit_hist, savings, checking, net_worth, total_assets, total_liab,
    stl_ratio, bankrupt, prev_def, missed_flag, high_util,
    loan_amt, loan_dur, base_rate, int_rate, monthly_lp, emi_ratio,
    lp_debt, lp_edu, lp_home, lp_oth,
    X_train, y_train,
    firestore_doc_id=None,
):
    with st.spinner("Running risk assessment..."):
        raw_input = {
            "Age": age, "AnnualIncome": annual_inc, "CreditScore": credit_score,
            "Experience": experience, "LoanAmount": loan_amt, "LoanDuration": loan_dur,
            "NumberOfDependents": dependents, "MonthlyDebtPayments": monthly_debt,
            "CreditCardUtilizationRate": cc_util, "NumberOfOpenCreditLines": open_lines,
            "NumberOfCreditInquiries": inquiries, "DebtToIncomeRatio": dti,
            "BankruptcyHistory": bankrupt, "PreviousLoanDefaults": prev_def,
            "PaymentHistory": pay_hist, "LengthOfCreditHistory": credit_hist,
            "SavingsAccountBalance": savings, "CheckingAccountBalance": checking,
            "TotalAssets": total_assets, "TotalLiabilities": total_liab,
            "MonthlyIncome": monthly_inc, "UtilityBillsPaymentHistory": util_hist,
            "JobTenure": job_tenure, "NetWorth": net_worth,
            "BaseInterestRate": base_rate, "InterestRate": int_rate,
            "MonthlyLoanPayment": monthly_lp, "TotalDebtToIncomeRatio": total_dti,
            "MissedPaymentFlag": missed_flag, "HighUtilizationFlag": high_util,
            "SavingsToLoanRatio": stl_ratio,
            "EmploymentStatus_Self-Employed": emp_self, "EmploymentStatus_Unemployed": emp_unemp,
            "EducationLevel_Bachelor": edu_bach, "EducationLevel_Doctorate": edu_doc,
            "EducationLevel_High School": edu_hs, "EducationLevel_Master": edu_mast,
            "MaritalStatus_Married": mar_marr, "MaritalStatus_Single": mar_sing,
            "MaritalStatus_Widowed": mar_wid,
            "HomeOwnershipStatus_Other": home_oth, "HomeOwnershipStatus_Own": home_own,
            "HomeOwnershipStatus_Rent": home_rent,
            "LoanPurpose_Debt Consolidation": lp_debt, "LoanPurpose_Education": lp_edu,
            "LoanPurpose_Home": lp_home, "LoanPurpose_Other": lp_oth,
        }

        all_columns  = X_train.columns.tolist()
        applicant_df = pd.DataFrame([{col: raw_input.get(col, 0.0) for col in all_columns}])
        applicant_df["EMIBurdenRatio"] = emi_ratio

        guard = predict_with_guard(applicant_df)

        st.session_state["applicant_id"]     = applicant_id
        st.session_state["guard"]            = guard
        st.session_state["raw_input"]        = raw_input
        st.session_state["firestore_doc_id"] = firestore_doc_id

        if guard["flag"]:
            st.warning(f"⚠️ Hard Rule Triggered — {guard['reason']}")
            st.error("Application blocked by risk guard.")
            return

        result = explain(
            applicant_data=raw_input,
            risk_score=guard["risk_score"],
            applicant_id=applicant_id,
            X_train=X_train,
            y_train=y_train,
        )
        st.session_state["result"] = result

    # ── Display results ─────────────────────────────────────────────────────
    st.divider()
    result       = st.session_state["result"]
    guard        = st.session_state["guard"]
    tier         = result["tier"]
    score        = result["risk_score"]
    default_risk = 1 - score

    st.markdown(
        f"""<div style="background-color:{tier['color']}22;border-left:6px solid {tier['color']};
            border-radius:8px;padding:16px 20px;margin-bottom:16px;">
            <span style="font-size:22px;font-weight:700;color:{tier['color']}">{tier['label']}</span><br>
            <span style="color:#6B7280;font-size:14px;">Applicant ID: {applicant_id}</span>
        </div>""", unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Default Risk",  f"{default_risk*100:.1f}%")
    col2.metric("AI Decision",   "Approve" if guard["approved"] else "Reject")
    col3.metric("Risk Tier",     tier["tier"])
    st.progress(float(default_risk),
                text=f"Default Risk: {default_risk*100:.1f}%  |  Approval Probability: {score*100:.1f}%")
    st.divider()

    st.subheader("🔑 Top Factors")
    for factor in result["top_factors"]:
        arrow   = "↓" if factor["direction"] == "raises" else "↑"
        color   = "#EF4444" if factor["direction"] == "raises" else "#10B981"
        badge_c = {"high": "#EF4444", "medium": "#F59E0B", "low": "#6B7280"}.get(
            factor["impact"], "#6B7280"
        )
        st.markdown(
            f"""<div style="display:flex;align-items:center;gap:12px;padding:8px 0;">
                <span style="font-size:20px;color:{color};font-weight:700">{arrow}</span>
                <div><strong>{factor['label']}</strong>
                &nbsp;<code>{factor['value']:.2f}</code>
                &nbsp;<span style="background:{badge_c};color:white;border-radius:4px;
                    padding:2px 8px;font-size:12px;">{factor['impact'].upper()}</span><br>
                <span style="color:#6B7280;font-size:13px;">{factor['summary']}</span></div>
            </div>""", unsafe_allow_html=True
        )
    st.divider()

    col_w, col_f = st.columns(2)
    with col_w:
        st.subheader("SHAP Waterfall")
        if result.get("waterfall_plot"):
            st.pyplot(result["waterfall_plot"])
    with col_f:
        st.subheader(" ")
        if result.get("force_plot"):
            st.pyplot(result["force_plot"])
    st.divider()

    st.subheader("👥 Cohort Intelligence")
    cohort = result.get("cohort")
    if cohort and cohort.get("summary"):
        st.info(cohort["summary"])
    else:
        st.info("Cohort data not available.")

    cf = result.get("counterfactual")
    if cf and cf.get("feasible"):
        st.subheader("💡 What Would Change the Decision?")
        st.success(cf["summary"])
    st.divider()

    st.subheader("📝 Decision Brief")
    st.text_area("Copy-paste ready banker summary:", value=result["decision_brief"], height=120)
    st.divider()

    st.subheader("⚖️ Banker Override")
    st.caption("Your decision overrides the AI. All overrides are logged.")
    override_note = st.text_input(
        "Override reason / notes",
        placeholder="e.g. Medical emergency explained missed payments",
        key="override_note_input",
    )
    col_a, col_r = st.columns(2)
    with col_a:
        if st.button("✅ Approve (Override)", use_container_width=True,
                     type="primary", key="approve_btn"):
            log_override(applicant_id, "APPROVED", override_note, score)
            if firestore_doc_id:
                update_banker_decision(firestore_doc_id, "Approved", override_note)
            st.success(f"Override logged: **APPROVED** for {applicant_id}")
    with col_r:
        if st.button("❌ Reject (Override)", use_container_width=True, key="reject_btn"):
            log_override(applicant_id, "REJECTED", override_note, score)
            if firestore_doc_id:
                update_banker_decision(firestore_doc_id, "Rejected", override_note)
            st.success(f"Override logged: **REJECTED** for {applicant_id}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
st.title("📊 Banker Decision Panel")

tab_manual, tab_queue = st.tabs(["✏️ Manual Entry", "📋 From Application Queue"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — MANUAL ENTRY
# ─────────────────────────────────────────────────────────────────────────────
with tab_manual:
    st.caption("Manually enter applicant details for immediate analysis.")
    st.divider()

    applicant_id = st.text_input("Applicant ID", value="APP-2024-001", key="manual_appid")

    col_sample, col_clear = st.columns([3, 1])
    with col_sample:
        selected_sample = st.selectbox(
            "⚡ Load sample application (for demo)",
            ["— select —"] + list(SAMPLES.keys()),
            key="sample_select",
        )
    with col_clear:
        st.write("")
        st.write("")
        if st.button("🔄 Clear", use_container_width=True, key="clear_btn"):
            st.session_state.pop("sample", None)
            st.rerun()

    if selected_sample != "— select —":
        st.session_state["sample"] = selected_sample

    active_sample = st.session_state.get("sample")
    sd = SAMPLES[active_sample] if active_sample and active_sample in SAMPLES else {}

    if active_sample:
        st.info(f"✅ Loaded: **{active_sample}**")

    # ── FIX 1: field() clamps default to >= min_val ────────────────────────
    def field(label, key, min_val=0.0, max_val=None, step=1.0, fmt="%.2f", form_key=None):
        raw_default = float(sd.get(key, min_val))          # use min_val, NOT 0
        default     = max(raw_default, float(min_val))     # clamp up if needed
        kwargs = dict(label=label, value=default, step=float(step), format=fmt,
                      min_value=float(min_val), key=form_key or f"m_{key}")
        if max_val is not None:
            kwargs["max_value"] = float(max_val)
        return st.number_input(**kwargs)

    def checkbox(label, key, form_key=None):
        return int(st.checkbox(label, value=bool(sd.get(key, 0)), key=form_key or f"m_cb_{key}"))

    with st.form("banker_manual_form"):
        st.subheader("👤 Personal Information")
        c1, c2, c3 = st.columns(3)
        with c1:  age        = field("Age", "Age", 18, 85, 1, "%.0f")
        with c2:  dependents = field("Number of Dependents", "NumberOfDependents", 0, 10, 1, "%.0f")
        with c3:  experience = field("Years of Experience", "Experience", 0, 50, 1, "%.0f")
        c4, c5, c6 = st.columns(3)
        with c4:  job_tenure = field("Job Tenure (years)", "JobTenure", 0, 50, 1, "%.0f")
        with c5:  emp_self   = checkbox("Self-Employed", "EmploymentStatus_Self-Employed")
        with c6:  emp_unemp  = checkbox("Unemployed", "EmploymentStatus_Unemployed")

        st.markdown("**Education**")
        ec1, ec2, ec3, ec4 = st.columns(4)
        with ec1: edu_bach = checkbox("Bachelor",    "EducationLevel_Bachelor")
        with ec2: edu_doc  = checkbox("Doctorate",   "EducationLevel_Doctorate")
        with ec3: edu_hs   = checkbox("High School", "EducationLevel_High School")
        with ec4: edu_mast = checkbox("Master",      "EducationLevel_Master")

        st.markdown("**Marital Status**")
        mc1, mc2, mc3 = st.columns(3)
        with mc1: mar_marr = checkbox("Married", "MaritalStatus_Married")
        with mc2: mar_sing = checkbox("Single",  "MaritalStatus_Single")
        with mc3: mar_wid  = checkbox("Widowed", "MaritalStatus_Widowed")

        st.markdown("**Home Ownership**")
        hc1, hc2, hc3 = st.columns(3)
        with hc1: home_own  = checkbox("Own",   "HomeOwnershipStatus_Own")
        with hc2: home_rent = checkbox("Rent",  "HomeOwnershipStatus_Rent")
        with hc3: home_oth  = checkbox("Other", "HomeOwnershipStatus_Other")
        st.divider()

        st.subheader("💰 Financial Profile")
        fc1, fc2, fc3 = st.columns(3)
        with fc1: annual_inc   = field("Annual Income (₹)",            "AnnualIncome",              0,   step=1000,  fmt="%.0f")
        with fc2: monthly_inc  = field("Monthly Income (₹)",           "MonthlyIncome",             0,   step=500,   fmt="%.0f")
        with fc3: credit_score = field("Credit Score",                 "CreditScore",               300, 900, 1,    "%.0f")
        fc4, fc5, fc6 = st.columns(3)
        with fc4: monthly_debt = field("Monthly Debt Payments (₹)",    "MonthlyDebtPayments",       0,   step=100,   fmt="%.0f")
        with fc5: cc_util      = field("Credit Card Utilization (0–1)","CreditCardUtilizationRate", 0.0, 1.0, 0.01)
        with fc6: open_lines   = field("Open Credit Lines",            "NumberOfOpenCreditLines",   0,   step=1,     fmt="%.0f")
        fc7, fc8, fc9 = st.columns(3)
        with fc7: inquiries    = field("Credit Inquiries",             "NumberOfCreditInquiries",   0,   step=1,     fmt="%.0f")
        with fc8: dti          = field("Debt-to-Income Ratio (0–1)",   "DebtToIncomeRatio",         0.0, 1.5, 0.01)
        # FIX 4: total_dti removed from form — auto-calculated after submit
        fc10, fc11, fc12 = st.columns(3)
        with fc10: pay_hist    = field("Payment History (0–1)",        "PaymentHistory",            0.0, 1.0, 0.01)
        with fc11: util_hist   = field("Utility Bills Payment (0–1)",  "UtilityBillsPaymentHistory",0.0, 1.0, 0.01)
        with fc12: credit_hist = field("Credit History Length (yrs)",  "LengthOfCreditHistory",     0,   step=1,     fmt="%.0f")
        fc13, fc14, fc15 = st.columns(3)
        with fc13: savings     = field("Savings Account Balance (₹)",  "SavingsAccountBalance",     0,   step=1000,  fmt="%.0f")
        with fc14: checking    = field("Checking Account Balance (₹)", "CheckingAccountBalance",    0,   step=500,   fmt="%.0f")
        with fc15: net_worth   = field("Net Worth (₹)",                "NetWorth",                  min_val=-10_000_000, step=1000, fmt="%.0f")
        fc16, fc17, fc18 = st.columns(3)
        with fc16: total_assets = field("Total Assets (₹)",     "TotalAssets",      0, step=1000, fmt="%.0f")
        with fc17: total_liab   = field("Total Liabilities (₹)","TotalLiabilities", 0, step=1000, fmt="%.0f")
        # stl_ratio auto-calculated — removed from form
        fc19, fc20, fc21 = st.columns(3)
        with fc19: bankrupt    = checkbox("Bankruptcy History",  "BankruptcyHistory")
        with fc20: prev_def    = field("Previous Loan Defaults", "PreviousLoanDefaults", 0, step=1, fmt="%.0f")
        with fc21: missed_flag = checkbox("Missed Payment Flag", "MissedPaymentFlag")
        high_util = checkbox("High Utilization Flag", "HighUtilizationFlag")
        st.divider()

        # ── FIX 4: Loan section — only ask what a banker would know ──────────
        st.subheader("🏦 Loan Details")
        st.caption(
            "💡 Interest rate, EMI, EMI burden ratio and total DTI are "
            "auto-calculated from credit score, loan amount and duration."
        )
        lc1, lc2 = st.columns(2)
        with lc1: loan_amt = field("Loan Amount (₹)",      "LoanAmount",  0,   step=1000, fmt="%.0f")
        with lc2: loan_dur = field("Loan Duration (months)","LoanDuration",6,  360, 6,   "%.0f")

        st.markdown("**Loan Purpose**")
        lp1, lp2, lp3, lp4 = st.columns(4)
        with lp1: lp_debt = checkbox("Debt Consolidation", "LoanPurpose_Debt Consolidation")
        with lp2: lp_edu  = checkbox("Education",          "LoanPurpose_Education")
        with lp3: lp_home = checkbox("Home",               "LoanPurpose_Home")
        with lp4: lp_oth  = checkbox("Other",              "LoanPurpose_Other")
        st.divider()

        manual_submitted = st.form_submit_button("🔍 Analyse Application", use_container_width=True)

    if manual_submitted:
        # ── FIX 4: Auto-calculate loan fields (same logic as 3_User_Apply.py) ─
        spread_pct   = credit_spread(credit_score)
        int_rate_pct = BASE_RATE_PCT + spread_pct
        monthly_lp   = calc_emi(loan_amt, int_rate_pct, int(loan_dur))
        base_rate    = BASE_RATE_PCT / 100.0
        int_rate     = int_rate_pct  / 100.0

        if monthly_inc > 0:
            emi_ratio = monthly_lp / monthly_inc
            total_dti = (monthly_debt + monthly_lp) / monthly_inc
        else:
            emi_ratio = 0.0
            total_dti = dti  # fallback to manually entered DTI

        stl_ratio = min(savings / (loan_amt + 1e-5), 10.0)

        # Show auto-calculated summary
        st.info(
            f"**Auto-calculated loan terms:**  \n"
            f"- Interest Rate: **{int_rate_pct:.1f}%** p.a. "
            f"(Base {BASE_RATE_PCT}% + {spread_pct}% risk spread)  \n"
            f"- Monthly EMI: **₹{round(monthly_lp):,}**  \n"
            f"- EMI Burden Ratio: **{emi_ratio:.2f}**  \n"
            f"- Total DTI (with new loan): **{total_dti:.2f}**"
        )

        _run_analysis(
            applicant_id=applicant_id,
            age=age, dependents=dependents, experience=experience,
            job_tenure=job_tenure, emp_self=emp_self, emp_unemp=emp_unemp,
            edu_bach=edu_bach, edu_doc=edu_doc, edu_hs=edu_hs, edu_mast=edu_mast,
            mar_marr=mar_marr, mar_sing=mar_sing, mar_wid=mar_wid,
            home_own=home_own, home_rent=home_rent, home_oth=home_oth,
            annual_inc=annual_inc, monthly_inc=monthly_inc, credit_score=credit_score,
            monthly_debt=monthly_debt, cc_util=cc_util, open_lines=open_lines,
            inquiries=inquiries, dti=dti, total_dti=total_dti,
            pay_hist=pay_hist, util_hist=util_hist, credit_hist=credit_hist,
            savings=savings, checking=checking, net_worth=net_worth,
            total_assets=total_assets, total_liab=total_liab, stl_ratio=stl_ratio,
            bankrupt=bankrupt, prev_def=prev_def, missed_flag=missed_flag,
            high_util=high_util,
            loan_amt=loan_amt, loan_dur=loan_dur, base_rate=base_rate,
            int_rate=int_rate, monthly_lp=monthly_lp, emi_ratio=emi_ratio,
            lp_debt=lp_debt, lp_edu=lp_edu, lp_home=lp_home, lp_oth=lp_oth,
            X_train=X_train, y_train=y_train,
        )

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — FROM QUEUE
# ─────────────────────────────────────────────────────────────────────────────
with tab_queue:
    st.caption("Select a pending application from the queue to run full analysis.")

    # ── FIX 3: Refresh queue_selected_app_id from URL param as fallback ───────
    # st.switch_page preserves session_state within the same browser session,
    # but display it clearly so banker knows what's loaded.
    queue_app_id = st.session_state.get("queue_selected_app_id")

    if not queue_app_id:
        st.info("No application selected from queue. Go to **📋 Application Queue** and click Analyse.")
    else:
        # ── FIX 3: Always re-fetch from Firestore so we get live data ─────────
        with st.spinner(f"Loading application {queue_app_id[:12]}..."):
            app_data = get_application(queue_app_id)

        if not app_data:
            st.error(f"Application `{queue_app_id}` not found in database.")
            if st.button("🔄 Clear selection"):
                st.session_state.pop("queue_selected_app_id", None)
                st.rerun()
        else:
            raw = app_data.get("raw_input", {})
            disp = app_data.get("display_input", {})

            st.success(
                f"Loaded application **{queue_app_id[:16]}...** "
                f"from {app_data.get('user_email', '?')} "
                f"({app_data.get('applicant_name', 'Unknown')})"
            )

            # ── Show key details from the application ─────────────────────────
            st.markdown("#### 📋 Application Summary")
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Loan Amount",   f"₹{int(raw.get('LoanAmount', 0)):,}")
            s2.metric("Credit Score",  int(raw.get("CreditScore", 0)))
            s3.metric("Annual Income", f"₹{int(raw.get('AnnualIncome', 0)):,}")
            s4.metric("Status",        app_data.get("status", "Pending"))

            s5, s6, s7, s8 = st.columns(4)
            s5.metric("Interest Rate",  disp.get("InterestRate", "—"))
            s6.metric("Monthly EMI",    f"₹{int(raw.get('MonthlyLoanPayment', 0)):,}")
            s7.metric("EMI Burden",     disp.get("EMIBurdenRatio", "—"))
            s8.metric("Loan Duration",  disp.get("LoanDuration", "—"))

            st.divider()

            col_run, col_clear = st.columns([3, 1])
            with col_run:
                run_btn = st.button(
                    "🔍 Run Full Analysis", type="primary",
                    key="queue_analyse_btn", use_container_width=True
                )
            with col_clear:
                if st.button("✖ Clear", key="queue_clear_btn", use_container_width=True):
                    st.session_state.pop("queue_selected_app_id", None)
                    st.rerun()

            if run_btn:
                # ── FIX 3: Use raw_input values directly from Firestore ───────
                # These are exactly what 3_User_Apply.py saved — model-ready decimals
                st.session_state["queue_analysis_done"] = True
                st.session_state["queue_firestore_doc_id"] = queue_app_id
                _run_analysis(
                    applicant_id=queue_app_id,
                    age=raw.get("Age", 30),
                    dependents=raw.get("NumberOfDependents", 0),
                    experience=raw.get("Experience", 0),
                    job_tenure=raw.get("JobTenure", 0),
                    emp_self=raw.get("EmploymentStatus_Self-Employed", 0),
                    emp_unemp=raw.get("EmploymentStatus_Unemployed", 0),
                    edu_bach=raw.get("EducationLevel_Bachelor", 0),
                    edu_doc=raw.get("EducationLevel_Doctorate", 0),
                    edu_hs=raw.get("EducationLevel_High School", 0),
                    edu_mast=raw.get("EducationLevel_Master", 0),
                    mar_marr=raw.get("MaritalStatus_Married", 0),
                    mar_sing=raw.get("MaritalStatus_Single", 0),
                    mar_wid=raw.get("MaritalStatus_Widowed", 0),
                    home_own=raw.get("HomeOwnershipStatus_Own", 0),
                    home_rent=raw.get("HomeOwnershipStatus_Rent", 0),
                    home_oth=raw.get("HomeOwnershipStatus_Other", 0),
                    annual_inc=raw.get("AnnualIncome", 0),
                    monthly_inc=raw.get("MonthlyIncome", 0),
                    credit_score=raw.get("CreditScore", 600),
                    monthly_debt=raw.get("MonthlyDebtPayments", 0),
                    cc_util=raw.get("CreditCardUtilizationRate", 0),
                    open_lines=raw.get("NumberOfOpenCreditLines", 0),
                    inquiries=raw.get("NumberOfCreditInquiries", 0),
                    dti=raw.get("DebtToIncomeRatio", 0),
                    total_dti=raw.get("TotalDebtToIncomeRatio", 0),
                    pay_hist=raw.get("PaymentHistory", 0),
                    util_hist=raw.get("UtilityBillsPaymentHistory", 0),
                    credit_hist=raw.get("LengthOfCreditHistory", 0),
                    savings=raw.get("SavingsAccountBalance", 0),
                    checking=raw.get("CheckingAccountBalance", 0),
                    net_worth=raw.get("NetWorth", 0),
                    total_assets=raw.get("TotalAssets", 0),
                    total_liab=raw.get("TotalLiabilities", 0),
                    stl_ratio=raw.get("SavingsToLoanRatio", 0),
                    bankrupt=raw.get("BankruptcyHistory", 0),
                    prev_def=raw.get("PreviousLoanDefaults", 0),
                    missed_flag=raw.get("MissedPaymentFlag", 0),
                    high_util=raw.get("HighUtilizationFlag", 0),
                    loan_amt=raw.get("LoanAmount", 0),
                    loan_dur=raw.get("LoanDuration", 36),
                    base_rate=raw.get("BaseInterestRate", 0.07),
                    int_rate=raw.get("InterestRate", 0.12),
                    monthly_lp=raw.get("MonthlyLoanPayment", 0),
                    emi_ratio=raw.get("TotalDebtToIncomeRatio", 0),  # stored as decimal
                    lp_debt=raw.get("LoanPurpose_Debt Consolidation", 0),
                    lp_edu=raw.get("LoanPurpose_Education", 0),
                    lp_home=raw.get("LoanPurpose_Home", 0),
                    lp_oth=raw.get("LoanPurpose_Other", 0),
                    X_train=X_train,
                    y_train=y_train,
                    firestore_doc_id=queue_app_id,
                )

            elif st.session_state.get("queue_analysis_done") and st.session_state.get("result"):
                result = st.session_state["result"]
                guard = st.session_state["guard"]
                stored_doc_id = st.session_state.get("queue_firestore_doc_id")

                st.subheader("⚖️ Banker Override")
                st.caption("Your decision overrides the AI. All overrides are logged.")

                override_note = st.text_input(
                    "Override reason / notes",
                    placeholder="e.g. Medical emergency explained missed payments",
                    key="override_note_queue",
                )

                col_a, col_r = st.columns(2)

                with col_a:
                    if st.button(
                        "✅ Approve (Override)",
                        use_container_width=True,
                        type="primary",
                        key="approve_btn_queue"
                    ):
                        log_override(stored_doc_id, "APPROVED", override_note, result["risk_score"])
                        update_banker_decision(stored_doc_id, "Approved", override_note)
                        st.success(f"Override logged: *APPROVED*")
                        st.session_state["queue_analysis_done"] = False

                with col_r:
                    if st.button(
                        "❌ Reject (Override)",
                        use_container_width=True,
                        key="reject_btn_queue"
                    ):
                        log_override(stored_doc_id, "REJECTED", override_note, result["risk_score"])
                        update_banker_decision(stored_doc_id, "Rejected", override_note)
                        st.success(f"Override logged: *REJECTED*")
                        st.session_state["queue_analysis_done"] = False