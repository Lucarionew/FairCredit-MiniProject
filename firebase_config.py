"""
firebase_config.py — FairCredit 2.0
====================================
Firebase Admin SDK initialisation + Firestore helpers.
Credentials are loaded from .streamlit/secrets.toml — NEVER hardcoded.

Firestore collection: "applications"
Each document fields:
    applicant_id        str
    submitted_by        str   (Firebase UID of the user)
    user_email          str
    status              str   "Pending" | "Approved" | "Rejected"
    banker_decision     str   "Approved" | "Rejected" | ""
    banker_note         str
    submitted_at        str   ISO timestamp
    decided_at          str   ISO timestamp or ""
    raw_input           dict  all 47 model features (model-ready, scaled internally)
    display_input       dict  human-friendly values shown to user
"""

import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore
from datetime import datetime, timezone


# ── Initialise Firebase Admin SDK once ────────────────────────────────────────
def _init_firebase():
    if firebase_admin._apps:
        return  # already initialised

    cfg = st.secrets["firebase"]
    cred_dict = {
        "type":                        cfg["type"],
        "project_id":                  cfg["project_id"],
        "private_key_id":              cfg["private_key_id"],
        "private_key":                 cfg["private_key"].replace("\\n", "\n"),
        "client_email":                cfg["client_email"],
        "client_id":                   cfg["client_id"],
        "auth_uri":                    cfg["auth_uri"],
        "token_uri":                   cfg["token_uri"],
        "auth_provider_x509_cert_url": cfg["auth_provider_x509_cert_url"],
        "client_x509_cert_url":        cfg["client_x509_cert_url"],
    }
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)


def get_db():
    _init_firebase()
    return firestore.client()


# ── Auth helpers ───────────────────────────────────────────────────────────────

def verify_id_token(id_token: str):
    """Verify a Firebase ID token and return the decoded token dict, or None."""
    _init_firebase()
    try:
        decoded = auth.verify_id_token(id_token)
        return decoded
    except Exception:
        return None


def get_user_by_email(email: str):
    """Return Firebase user record or None."""
    _init_firebase()
    try:
        return auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        return None


def get_user_role(uid: str) -> str:
    """
    Return role for a given UID.
    Roles stored as custom claims: {"role": "banker"} or {"role": "user"}.
    Default to "user" if no claim set.
    """
    _init_firebase()
    try:
        user = auth.get_user(uid)
        claims = user.custom_claims or {}
        return claims.get("role", "user")
    except Exception:
        return "user"


def set_user_role(uid: str, role: str):
    """Set custom claim role for a user. Call once after creating banker accounts."""
    _init_firebase()
    auth.set_custom_user_claims(uid, {"role": role})


# ── Firestore application helpers ──────────────────────────────────────────────

COLLECTION = "applications"


def submit_application(
    uid: str,
    email: str,
    applicant_name: str,
    raw_input: dict,
    display_input: dict,
) -> str:
    """
    Write a new loan application to Firestore.
    Returns the generated document ID (used as applicant_id).
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    doc_ref = db.collection(COLLECTION).document()
    doc_ref.set({
        "applicant_id":    doc_ref.id,
        "submitted_by":    uid,
        "user_email":      email,
        "applicant_name":  applicant_name,
        "status":          "Pending",
        "banker_decision": "",
        "banker_note":     "",
        "submitted_at":    now,
        "decided_at":      "",
        "raw_input":       raw_input,
        "display_input":   display_input,
    })
    return doc_ref.id


def get_application(doc_id: str):
    """Fetch a single application by document ID."""
    db = get_db()
    doc = db.collection(COLLECTION).document(doc_id).get()
    return doc.to_dict() if doc.exists else None


def get_applications_by_user(uid: str) -> list:
    """
    Return all applications submitted by a specific user, newest first.

    NOTE: We intentionally avoid combining .where() + .order_by() on different
    fields because that requires a Firestore composite index to be manually
    created in the Firebase Console. Instead, we filter by 'submitted_by' only
    and sort the results in Python — this works without any index configuration.
    """
    db = get_db()
    docs = (
        db.collection(COLLECTION)
        .where("submitted_by", "==", uid)
        .stream()
    )
    results = [d.to_dict() for d in docs]
    # Sort newest-first in Python — no composite index required
    results.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
    return results


def get_all_applications(status_filter=None) -> list:
    """
    Return all applications. Optionally filter by status.
    status_filter: "Pending" | "Approved" | "Rejected" | None (all)

    NOTE: Same approach — avoid compound query, sort in Python to prevent
    requiring a Firestore composite index.
    """
    db = get_db()
    ref = db.collection(COLLECTION)
    if status_filter:
        ref = ref.where("status", "==", status_filter)
    docs = ref.stream()
    results = [d.to_dict() for d in docs]
    results.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
    return results


def update_banker_decision(doc_id: str, decision: str, note: str):
    """
    Banker approves or rejects. Updates status, decision, note, decided_at.
    decision: "Approved" | "Rejected"
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    db.collection(COLLECTION).document(doc_id).update({
        "status":          decision,
        "banker_decision": decision,
        "banker_note":     note,
        "decided_at":      now,
    })