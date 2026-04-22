"""
pages/4_User_Status.py — FairCredit 2.0
========================================
User-facing status page.
Shows all applications the user has submitted, with:
  - Current status (Pending / Approved / Rejected)
  - Banker's override decision and written note
  - Key submitted details (in human-friendly display units)
"""

import streamlit as st
from datetime import datetime

# ── Auth guard ─────────────────────────────────────────────────────────────────
if not st.session_state.get("logged_in"):
    st.warning("Please sign in from the Home page.")
    st.stop()
if st.session_state.get("role") != "user":
    st.error("This page is for applicants only.")
    st.stop()

from firebase_config import get_applications_by_user

uid = st.session_state["uid"]

# ── Page ───────────────────────────────────────────────────────────────────────
st.title("📬 My Application Status")
st.caption("Track the status of your loan applications and view banker decisions.")
st.divider()

col_ref, _ = st.columns([1, 4])
with col_ref:
    if st.button("🔄 Refresh Status"):
        st.rerun()

# ── Fetch user's applications ──────────────────────────────────────────────────
with st.spinner("Loading your applications..."):
    try:
        applications = get_applications_by_user(uid)
    except Exception as e:
        st.error(f"Could not load applications: {e}")
        applications = []

if not applications:
    st.info("You haven't submitted any loan applications yet.")
    st.page_link("pages/3_User_Apply.py", label="📝 Apply for a Loan", icon="📝")
    st.stop()

# ── Helper ─────────────────────────────────────────────────────────────────────
def _fmt_ts(ts):
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y, %H:%M")
    except Exception:
        return ts[:16]

STATUS_CONFIG = {
    "Pending": {
        "color":   "#F59E0B",
        "bg":      "#F59E0B11",
        "icon":    "⏳",
        "message": "Your application is under review by our banking team. We'll update you soon.",
    },
    "Approved": {
        "color":   "#10B981",
        "bg":      "#10B98111",
        "icon":    "✅",
        "message": "Congratulations! Your loan application has been approved.",
    },
    "Rejected": {
        "color":   "#EF4444",
        "bg":      "#EF444411",
        "icon":    "❌",
        "message": "We regret to inform you that your application was not approved at this time.",
    },
}

# ── Render each application ────────────────────────────────────────────────────
for i, app in enumerate(applications):
    app_id      = app.get("applicant_id", "N/A")
    status      = app.get("status", "Pending")
    submitted_at= app.get("submitted_at", "")
    decided_at  = app.get("decided_at", "")
    decided_text = f"  •  Decided: {_fmt_ts(decided_at)}" if decided_at else ""
    banker_note = app.get("banker_note", "")
    display     = app.get("display_input", {})
    short_id    = app_id[:12] + "..." if len(app_id) > 12 else app_id

    cfg   = STATUS_CONFIG.get(status, STATUS_CONFIG["Pending"])
    color = cfg["color"]
    icon  = cfg["icon"]

    # ── Status banner ──────────────────────────────────────────────────────────
    st.markdown(
        f"""<div style="background:{cfg['bg']};border:1px solid {color}44;
            border-left:6px solid {color};border-radius:10px;
            padding:20px 24px;margin-bottom:8px;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div>
                    <span style="font-size:20px;font-weight:800;color:{color};">
                        {icon} {status}
                    </span><br>
                    <span style="font-size:13px;color:#9CA3AF;">
                        Application ID: {short_id}
                    </span>
                </div>
                <div style="text-align:right;font-size:12px;color:#6B7280;">
                    Submitted: {_fmt_ts(submitted_at)}{decided_text}
                </div>
            </div>
            <p style="margin-top:12px;color:#D1D5DB;font-size:14px;">{cfg['message']}</p>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Banker's decision note ─────────────────────────────────────────────────
    if status != "Pending" and banker_note:
        st.markdown(
            f"""<div style="background:#1e2130;border:1px solid #2d3250;
                border-radius:8px;padding:16px 20px;margin-bottom:12px;">
                <span style="font-size:13px;font-weight:700;color:#94A3B8;">
                    📝 Banker's Note:
                </span><br>
                <span style="font-size:15px;color:#E2E8F0;font-style:italic;">
                    "{banker_note}"
                </span>
            </div>""",
            unsafe_allow_html=True,
        )
    elif status != "Pending" and not banker_note:
        st.caption("No additional note from the banker.")

    # ── Application summary (expandable) ──────────────────────────────────────
    with st.expander(f"📋 View your submitted details — Application {short_id}"):
        if not display:
            st.caption("Display data not available.")
        else:
            st.markdown("#### Personal Details")
            pd1, pd2, pd3 = st.columns(3)
            pd1.metric("Name",       display.get("ApplicantName", "—"))
            pd2.metric("Age",        display.get("Age", "—"))
            pd3.metric("Employment", display.get("EmploymentStatus", "—"))

            pd4, pd5, pd6 = st.columns(3)
            pd4.metric("Education",    display.get("EducationLevel", "—"))
            pd5.metric("Marital Status", display.get("MaritalStatus", "—"))
            pd6.metric("Home",         display.get("HomeOwnership", "—"))

            st.markdown("#### Financial Profile")
            fi1, fi2, fi3 = st.columns(3)
            ann = display.get("AnnualIncome")
            fi1.metric("Annual Income",    f"₹{ann:,}" if isinstance(ann, (int, float)) else "—")
            mon = display.get("MonthlyIncome")
            fi2.metric("Monthly Income",   f"₹{mon:,}" if isinstance(mon, (int, float)) else "—")
            fi3.metric("Credit Score",     str(display.get("CreditScore", "—")))

            fi4, fi5, fi6 = st.columns(3)
            fi4.metric("Debt-to-Income",   display.get("DebtToIncomeRatio", "—"))
            fi5.metric("Payment History",  display.get("PaymentHistory", "—"))
            sav = display.get("SavingsBalance")
            fi6.metric("Savings Balance",  f"₹{sav:,}" if isinstance(sav, (int, float)) else "—")

            st.markdown("#### Loan Request")
            li1, li2, li3 = st.columns(3)
            lamt = display.get("LoanAmount")
            li1.metric("Loan Amount",    f"₹{lamt:,}" if isinstance(lamt, (int, float)) else "—")
            li2.metric("Duration",       display.get("LoanDuration", "—"))
            li3.metric("Purpose",        display.get("LoanPurpose", "—"))

            li4, li5, li6 = st.columns(3)
            li4.metric("Interest Rate",  display.get("InterestRate", "—"))
            emi = display.get("MonthlyEMI")
            li5.metric("Monthly EMI",    f"₹{emi:,}" if isinstance(emi, (int, float)) else "—")
            li6.metric("EMI Burden",     display.get("EMIBurdenRatio", "—"))

    st.divider()

# ── Apply again button ─────────────────────────────────────────────────────────
st.markdown("**Want to submit a new application?**")
if st.button("📝 Submit New Application"):
    st.session_state.pop("application_submitted", None)
    st.session_state.pop("last_submitted_app_id", None)
    st.switch_page("pages/3_User_Apply.py")