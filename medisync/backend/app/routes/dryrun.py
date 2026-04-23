# dryrun.py — /dryrun router
# Endpoints:
#   POST /dryrun/run           → Validates selected resources without pushing
# Dry run logic:
#   1. Patient uniqueness check (search DrChrono DB)
#   2. API call count estimator
#   3. Rate limit calculator (500/day, 29/min)
#   4. Per-resource row-level validation (Pass/Fail)
#   5. Edge case detection
# Returns: DryRunReport schema

# TODO: implement
