"""
Token-basierte Auth via SHA-256 Hash
.htaccess schützt als erste Schicht, dieser Token als zweite
"""

import os
import hashlib
import hmac


def verify_token(token: str) -> bool:
    """Vergleicht SHA-256(token) gegen API_TOKEN_HASH aus .env"""
    expected_hash = os.environ.get("API_TOKEN_HASH", "")
    if not expected_hash:
        return False

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    # Timing-sicherer Vergleich
    return hmac.compare_digest(token_hash, expected_hash)
