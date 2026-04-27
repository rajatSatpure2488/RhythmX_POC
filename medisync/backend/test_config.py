"""
Standalone diagnostic test — run from medisync/ directory:
  python backend/test_config.py
"""
import sys, os
sys.path.insert(0, 'backend')

SEP = "=" * 60

print(SEP)
print("STEP 1: Import config (triggers load_dotenv at module level)")
print(SEP)
from app.core import config

print()
print(SEP)
print("STEP 2: Check values read by config module")
print(SEP)

client_id_display = (config.DRCHRONO_CLIENT_ID[:10] + "...") if config.DRCHRONO_CLIENT_ID else "EMPTY ❌"
secret_display    = "SET ✓ (hidden)" if config.DRCHRONO_CLIENT_SECRET else "EMPTY ❌"

print("  CLIENT_ID      :", client_id_display)
print("  CLIENT_SECRET  :", secret_display)
print("  REDIRECT_URI   :", config.DRCHRONO_REDIRECT_URI)
print("  FRONTEND_URL   :", config.FRONTEND_URL)

print()
print(SEP)
print("STEP 3: config.validate()")
print(SEP)
try:
    config.validate()
    print("  PASSED ✓")
except Exception as e:
    print("  FAILED ❌:", e)

print()
print(SEP)
print("STEP 4: Simulate DrChronoClient.get_authorization_url()")
print(SEP)
from app.services.drchrono_client import drchrono_client
try:
    url = drchrono_client.get_authorization_url("user:read")
    print("  auth_url (first 80 chars):", url[:80])
    print("  PASSED ✓")
except Exception as e:
    print("  FAILED ❌:", e)

print()
print(SEP)
print("STEP 5: os.getenv() direct check")
print(SEP)
direct = os.getenv("DRCHRONO_CLIENT_ID", "NOT IN ENV")
print("  os.getenv('DRCHRONO_CLIENT_ID') =", direct[:10] if direct != "NOT IN ENV" else direct)
