"""
pages/2_Banker_Queue.py — FairCredit 2.0
=========================================
Banker Application Queue.

FIX LOG:
  1. display_input key lookups match 3_User_Apply.py exactly
  2. Safe formatting for all metric values
  3. Single get_all_applications() call
  4. Analyse button: sets session_state key then switches page (reliable nav)
"""

import streamlit as st
import pandas as pd
from datetime import datetime

# ── Auth guard ─────────────────────────────────────────────────────────────────
if not st.session_state.get("logged_in"):
    st.warning("Please sign in from the Home page.")
    st.stop()
if st.session_state.get("role") != "banker":
    st.error("Access denied. This page is for bankers only.")
    st.stop()

from firebase_config import get_all_applications, update_banker_decision

# ── Page ───────────────────────────────────────────────────────────────────────
st.title("📋 Application Queue")
st.caption("All loan applications submitted by users. Click Analyse to run full SHAP analysis.")
st.divider()

# ── Filter controls ────────────────────────────────────────────────────────────
col_filter, col_refresh = st.columns([3, 1])
with col_filter:
    status_filter = st.selectbox(
        "Filter by status",
        ["All", "Pending", "Approved", "Rejected"],
        index=0,
    )
with col_refresh:
    st.write("")
    st.write("")
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

# ── Fetch all applications once ────────────────────────────────────────────────
with st.spinner("Loading applications..."):
    try:
        all_apps = get_all_applications()
    except Exception as e:
        st.error(f"Failed to load applications: {e}")
        all_apps = []

# Apply status filter in Python
if status_filter == "All":
    applications = all_apps
else:
    applications = [a for a in all_apps if a.get("status") == status_filter]

# ── Summary metrics ────────────────────────────────────────────────────────────
total    = len(all_apps)
pending  = sum(1 for a in all_apps if a.get("status") == "Pending")
approved = sum(1 for a in all_apps if a.get("status") == "Approved")
rejected = sum(1 for a in all_apps if a.get("status") == "Rejected")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Applications", total)
m2.metric("⏳ Pending",          pending)
m3.metric("✅ Approved",         approved)
m4.metric("❌ Rejected",         rejected)
st.divider()

if not applications:
    st.info("No applications found." + (f" (filter: {status_filter})" if status_filter != "All" else ""))
    st.stop()

# ── Helpers ────────────────────────────────────────────────────────────────────
STATUS_COLOR = {
    "Pending":  "#F59E0B",
    "Approved": "#10B981",
    "Rejected": "#EF4444",
}
STATUS_ICON = {
    "Pending":  "⏳",
    "Approved": "✅",
    "Rejected": "❌",
}

def _fmt_ts(ts):
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y, %H:%M")
    except Exception:
        return str(ts)[:16]

def _fmt_inr(val):
    if val is None:
        return "—"
    try:
        return f"₹{int(float(val)):,}"
    except (ValueError, TypeError):
        return str(val)

def _fmt_val(val, fallback="—"):
    if val is None:
        return fallback
    return str(val)

# ── Application cards ──────────────────────────────────────────────────────────
for app in applications:
    app_id       = app.get("applicant_id", "N/A")
    email        = app.get("user_email", "N/A")
    name         = app.get("applicant_name", "N/A")
    status       = app.get("status", "Pending")
    submitted_at = app.get("submitted_at", "")
    decided_at   = app.get("decided_at", "")
    banker_note  = app.get("banker_note", "")
    display      = app.get("display_input", {})
    raw          = app.get("raw_input", {})

    color = STATUS_COLOR.get(status, "#6B7280")
    icon  = STATUS_ICON.get(status, "•")

    with st.container():
        decided_text = f"  •  Decided: {_fmt_ts(decided_at)}" if decided_at else ""
        st.markdown(
            f"""<div style="border:1px solid {color}44;border-left:5px solid {color};
                border-radius:8px;padding:16px 20px;margin-bottom:12px;
                background:{'#1a1f2e' if status=='Pending' else '#141820'};">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <span style="font-size:16px;font-weight:700;color:#e2e8f0;">{name}</span>
                        &nbsp;<span style="font-size:12px;color:#6B7280;">{email}</span><br>
                        <span style="font-size:11px;color:#6B7280;">ID: {app_id[:20]}{'...' if len(app_id) > 20 else ''}</span>
                    </div>
                    <span style="font-size:14px;font-weight:700;color:{color};
                        background:{color}22;padding:4px 12px;border-radius:20px;">
                        {icon} {status}
                    </span>
                </div>
                <div style="margin-top:8px;font-size:12px;color:#9CA3AF;">
                    Submitted: {_fmt_ts(submitted_at)}{decided_text}
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

        # ── Metrics: prefer raw_input for numbers, display_input for formatted ─
        if raw or display:
            dc1, dc2, dc3, dc4, dc5 = st.columns(5)
            # FIX: read from raw_input for reliable numeric values
            dc1.metric("Loan Amount",   _fmt_inr(raw.get("LoanAmount",   display.get("LoanAmount"))))
            dc2.metric("Annual Income", _fmt_inr(raw.get("AnnualIncome", display.get("AnnualIncome"))))
            dc3.metric("Credit Score",  _fmt_val(raw.get("CreditScore",  display.get("CreditScore"))))
            dc4.metric("DTI",           _fmt_val(display.get("DebtToIncomeRatio", f"{raw.get('DebtToIncomeRatio', 0):.0%}")))
            dc5.metric("Defaults",      _fmt_val(raw.get("PreviousLoanDefaults", display.get("PreviousLoanDefaults"))))

            dr1, dr2, dr3, dr4, dr5 = st.columns(5)
            dr1.metric("Monthly EMI",   _fmt_inr(raw.get("MonthlyLoanPayment", display.get("MonthlyEMI"))))
            dr2.metric("Interest Rate", _fmt_val(display.get("InterestRate", f"{raw.get('InterestRate', 0):.1%}")))
            dr3.metric("EMI Burden",    _fmt_val(display.get("EMIBurdenRatio")))
            dr4.metric("Loan Duration", _fmt_val(display.get("LoanDuration", f"{int(raw.get('LoanDuration', 0))} months")))
            dr5.metric("Loan Purpose",  _fmt_val(display.get("LoanPurpose")))

        if banker_note and status != "Pending":
            st.caption(f"📝 Banker note: *{banker_note}*")

        # ── Action buttons ─────────────────────────────────────────────────────
        btn_col1, btn_col2, btn_col3 = st.columns([2, 1, 1])
        with btn_col1:
            # FIX 4: set session state key THEN switch page — guarantees it's set
            if st.button(
                "🔍 Analyse in Decision Panel",
                key=f"analyse_{app_id}",
                type="primary" if status == "Pending" else "secondary",
                use_container_width=True,
            ):
                st.session_state["queue_selected_app_id"] = app_id
                st.switch_page("pages/1_Banker_Dashboard.py")

        # Quick override (pending only)
        if status == "Pending":
            with btn_col2:
                if st.button("✅ Quick Approve", key=f"qapprove_{app_id}", use_container_width=True):
                    st.session_state[f"quick_action_{app_id}"] = "approve"
            with btn_col3:
                if st.button("❌ Quick Reject", key=f"qreject_{app_id}", use_container_width=True):
                    st.session_state[f"quick_action_{app_id}"] = "reject"

            qa = st.session_state.get(f"quick_action_{app_id}")
            if qa:
                note = st.text_input(
                    f"Note for quick {'approval' if qa == 'approve' else 'rejection'}:",
                    key=f"qnote_{app_id}",
                    placeholder="Brief reason..."
                )
                confirm_col, cancel_col = st.columns(2)
                with confirm_col:
                    if st.button("Confirm", key=f"qconfirm_{app_id}", type="primary"):
                        decision = "Approved" if qa == "approve" else "Rejected"
                        update_banker_decision(app_id, decision, note)
                        st.session_state.pop(f"quick_action_{app_id}", None)
                        st.success(f"Application {decision.lower()}.")
                        st.rerun()
                with cancel_col:
                    if st.button("Cancel", key=f"qcancel_{app_id}"):
                        st.session_state.pop(f"quick_action_{app_id}", None)
                        st.rerun()

        st.divider()