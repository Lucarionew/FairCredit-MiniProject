"""
app.py — FairCredit 2.0
========================
Entry point. Handles:
  1. Firebase Auth login / logout via REST API (email + password)
  2. Role detection (banker vs user) via custom claims
  3. Role-based sidebar navigation
  4. Session state management

All ML logic lives in pages/. This file never imports predict or explain.
"""

import streamlit as st
import requests
import json
from firebase_config import get_user_role, _init_firebase
import firebase_admin
from firebase_admin import auth as fb_auth

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FairCredit 2.0",
    layout="wide",
    page_icon="🏦",
    initial_sidebar_state="expanded",
)

# ── Firebase Web API key (from secrets) ───────────────────────────────────────
# Used only for email/password sign-in via REST — Admin SDK has no sign-in method
def _web_api_key() -> str:
    return st.secrets["firebase"]["web_api_key"]


# ── Email/password sign-in via Firebase Auth REST API ─────────────────────────
def _sign_in(email: str, password: str) -> dict | None:
    """
    Returns decoded token dict on success, None on failure.
    Uses Firebase Auth REST endpoint (signInWithPassword).
    """
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={_web_api_key()}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if "idToken" in data:
            return data          # contains idToken, localId (uid), email, refreshToken
        return None
    except Exception:
        return None


# ── Session state initialisation ──────────────────────────────────────────────
def _init_session():
    defaults = {
        "logged_in":   False,
        "uid":         None,
        "email":       None,
        "role":        None,       # "banker" | "user"
        "id_token":    None,
        "display_name": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── Login page ────────────────────────────────────────────────────────────────
def _show_login():
    # Custom CSS for a clean dark login card
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #0f1117 0%, #1a1f2e 50%, #0f1117 100%);
    }
    .login-card {
        max-width: 420px;
        margin: 60px auto 0 auto;
        background: #1e2130;
        border: 1px solid #2d3250;
        border-radius: 16px;
        padding: 40px 36px 32px 36px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    }
    .login-title {
        font-size: 28px;
        font-weight: 800;
        color: #e2e8f0;
        text-align: center;
        margin-bottom: 4px;
        letter-spacing: -0.5px;
    }
    .login-subtitle {
        font-size: 13px;
        color: #6b7280;
        text-align: center;
        margin-bottom: 28px;
    }
    </style>
    """, unsafe_allow_html=True)

    col_left, col_mid, col_right = st.columns([1, 2, 1])
    with col_mid:
        st.markdown("""
        <div class="login-card">
            <div class="login-title">🏦 FairCredit 2.0</div>
            <div class="login-subtitle">Fair & Explainable Loan AI</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("###")
        with st.form("login_form"):
            email    = st.text_input("Email", placeholder="you@example.com")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

        if submitted:
            if not email or not password:
                st.error("Please enter both email and password.")
                return

            with st.spinner("Signing in..."):
                result = _sign_in(email.strip(), password)

            if result is None:
                st.error("❌ Invalid email or password. Please try again.")
                return

            uid   = result["localId"]
            token = result["idToken"]

            # Get role from custom claims via Admin SDK
            _init_firebase()
            role = get_user_role(uid)

            st.session_state["logged_in"]    = True
            st.session_state["uid"]          = uid
            st.session_state["email"]        = result["email"]
            st.session_state["id_token"]     = token
            st.session_state["role"]         = role
            st.session_state["display_name"] = result.get("displayName", email.split("@")[0])
            st.rerun()


# ── Sidebar for logged-in users ───────────────────────────────────────────────
def _show_sidebar():
    role  = st.session_state["role"]
    email = st.session_state["email"]
    name  = st.session_state["display_name"]

    with st.sidebar:
        st.markdown(f"### 🏦 FairCredit 2.0")
        st.caption("*Fair & Explainable Loan AI*")
        st.divider()

        badge = "🔑 Banker" if role == "banker" else "👤 Applicant"
        st.markdown(f"**{badge}**")
        st.caption(f"{name}  •  {email}")
        st.divider()

        if role == "banker":
            st.markdown("**Banker Navigation**")
            st.page_link("pages/1_Banker_Dashboard.py", label="📊 Decision Panel",     icon="📊")
            st.page_link("pages/2_Banker_Queue.py",     label="📋 Application Queue",  icon="📋")
            st.page_link("pages/5_Banker_Audit.py",     label="🔍 Audit & Fairness",   icon="🔍")
        else:
            st.markdown("**My Navigation**")
            st.page_link("pages/3_User_Apply.py",  label="📝 Apply for Loan",    icon="📝")
            st.page_link("pages/4_User_Status.py", label="📬 My Application",    icon="📬")

        st.divider()
        if st.button("🚪 Sign Out", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


# ── Main ───────────────────────────────────────────────────────────────────────
_init_session()

if not st.session_state["logged_in"]:
    _show_login()
else:
    _show_sidebar()
    role = st.session_state["role"]

    # Landing page after login
    if role == "banker":
        st.title("🏦 Welcome back, Banker")
        st.markdown("""
        Use the **sidebar** to navigate:
        - **📊 Decision Panel** — analyse a submitted application with full SHAP explainability
        - **📋 Application Queue** — review pending applications submitted by users
        - **🔍 Audit & Fairness** — model performance, fairness metrics, override history
        """)
    else:
        st.title("🏦 Welcome to FairCredit")
        st.markdown("""
        Use the **sidebar** to navigate:
        - **📝 Apply for Loan** — fill in your application details and submit
        - **📬 My Application** — track your application status and see the banker's decision
        """)