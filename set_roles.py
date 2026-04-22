"""
set_roles.py — Run this ONCE to assign roles to Firebase users.
After running, you can delete this file.

Usage:
    python set_roles.py
"""

import firebase_admin
from firebase_admin import credentials, auth
import json

# ── Load your service account key directly (since we're running outside Streamlit)
with open("C:\\Users\\hp\\Downloads\\faircredit-b3d73-firebase-adminsdk-fbsvc-e9a319c495.json") as f:
    cred_dict = json.load(f)

cred = credentials.Certificate(cred_dict)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

# ── PASTE YOUR UIDs HERE ───────────────────────────────────────────────────────
# Get these from Firebase Console → Authentication → Users

BANKER_UID = "eabhSViDb8YJ8rAWOJJap3VsNou2"   # ← replace this
USER_UID   = "qApMyTOM7kWaZyr7EHNSBibL64E2"     # ← replace this (optional, user is default)

# ── Set roles ──────────────────────────────────────────────────────────────────
auth.set_custom_user_claims(BANKER_UID, {"role": "banker"})
print(f"✅ Banker role set for UID: {BANKER_UID}")

auth.set_custom_user_claims(USER_UID, {"role": "user"})
print(f"✅ User role set for UID: {USER_UID}")

# ── Verify ─────────────────────────────────────────────────────────────────────
banker = auth.get_user(BANKER_UID)
user   = auth.get_user(USER_UID)
print(f"\nVerification:")
print(f"  Banker ({banker.email}): {banker.custom_claims}")
print(f"  User   ({user.email}):   {user.custom_claims}")
print("\n✅ Done. You can delete set_roles.py now.")