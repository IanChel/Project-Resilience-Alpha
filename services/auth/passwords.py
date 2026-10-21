"""Password hashing for the human operator account (stdlib only)."""
import base64
import hashlib
import hmac
import secrets

ITERATIONS = 600_000

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split('$')
        if algorithm != 'pbkdf2_sha256': return False
        count = int(iterations)
        if not 100_000 <= count <= 2_000_000: return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, count)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False
