"""
pages/5_Banker_Audit.py — FairCredit 2.0
==========================================
Audit & Fairness Dashboard (banker only).
Original content from app.py Page 3, unchanged.
"""

import streamlit as st
import pandas as pd
import os

# ── Auth guard ─────────────────────────────────────────────────────────────────
if not st.session_state.get("logged_in"):
    st.warning("Please sign in from the Home page.")
    st.stop()
if st.session_state.get("role") != "banker":
    st.error("Access denied. This page is for bankers only.")
    st.stop()

OVERRIDES_FILE = "overrides.csv"

# ── Page ───────────────────────────────────────────────────────────────────────
st.title("🔍 Audit & Fairness Dashboard")
st.caption("Model performance, fairness metrics, and banker override history.")
st.divider()

st.subheader("📊 Fairness: Approval Rate by Age Group")
fairness_path = "reports/model/fairness_approval_by_agegroup.png"
if os.path.exists(fairness_path):
    st.image(fairness_path, use_container_width=True)
else:
    st.caption(f"Image not found at `{fairness_path}`")

col1, col2 = st.columns(2)
with col1:
    st.subheader("ROC Curve")
    roc_path = "reports/model/roc_curve.png"
    if os.path.exists(roc_path):
        st.image(roc_path, use_container_width=True)
    else:
        st.caption(f"Not found: `{roc_path}`")
with col2:
    st.subheader("Model Comparison")
    cmp_path = "reports/model/comparison.png"
    if os.path.exists(cmp_path):
        st.image(cmp_path, use_container_width=True)
    else:
        st.caption(f"Not found: `{cmp_path}`")

st.subheader("Confusion Matrix")
cm_path = "reports/model/confusion_matrix.png"
if os.path.exists(cm_path):
    st.image(cm_path, use_container_width=True)
else:
    st.caption(f"Not found: `{cm_path}`")
st.divider()

st.subheader("🎯 Target Benchmarks")
benchmarks = pd.DataFrame([
    {"Metric": "ROC-AUC",                 "Target": "> 0.85"},
    {"Metric": "F1-score (Approved=1)",    "Target": "> 0.70"},
    {"Metric": "Recall (Approved=1)",      "Target": "> 0.65"},
    {"Metric": "Demographic Parity Ratio", "Target": "> 0.80  (closer to 1 = fairer)"},
    {"Metric": "Equalized Odds Difference","Target": "< 0.10  (closer to 0 = fairer)"},
])
st.dataframe(benchmarks, use_container_width=True, hide_index=True)
st.divider()

st.subheader("📋 Banker Override Log")
if os.path.exists(OVERRIDES_FILE):
    overrides_df = pd.read_csv(OVERRIDES_FILE)
    st.dataframe(overrides_df, use_container_width=True)
    csv = overrides_df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download Override Log", csv, "overrides.csv", "text/csv")
else:
    st.info("No overrides logged yet.")