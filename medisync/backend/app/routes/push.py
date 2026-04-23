# push.py — /push router
# Endpoints:
#   POST /push/run             → Executes actual EHR push for selected resources
# Push logic:
#   1. Auto-validate if dry run not cached
#   2. Patient check: CREATE (POST) or UPDATE (PATCH)
#   3. Execute API calls per resource, rate-limited to 29/min
#   4. Track pass/fail per row with column-level error detail
# Returns: PushResults schema

# TODO: implement
