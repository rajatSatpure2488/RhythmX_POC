# upload.py — /upload router
# Endpoints:
#   POST /upload/zip    → Accepts ZIP file, extracts to temp dir
#   POST /upload/folder → Accepts multiple files (folder equivalent)
#   POST /upload/files  → Accepts arbitrary multi-file upload
#   POST /upload/load   → Triggers preprocessing: detect types,
#                          identify patient ID, link foreign keys,
#                          validate mandatory fields
# Returns patient summary and 13-resource inventory

# TODO: implement
