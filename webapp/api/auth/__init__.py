"""P4b: local-account auth (stdlib-only).

Password hashing uses ``hashlib.pbkdf2_hmac``; session tokens are HMAC-SHA256
signed payloads. No new third-party dependency (no passlib / jose / multipart).
"""
