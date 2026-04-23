# auth.py — /auth router
# Endpoints:
#   POST /auth/oauth/initiate  → Redirects to DrChrono OAuth page
#   GET  /auth/oauth/callback  → Exchanges auth code for access token
#   POST /auth/manual          → Accepts access_token + doctor_id directly
#   GET  /auth/status          → Returns current auth status
# Delegates token storage to services/token_store.py

# TODO: implement
