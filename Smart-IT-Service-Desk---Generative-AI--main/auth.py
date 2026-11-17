"""
auth.py
User authentication, registration, and PBKDF2 password security.
Uses PBKDF2-HMAC-SHA256 with 310,000 iterations and per-user random salt.
Constant-time verification using hmac.compare_digest.
"""

import hashlib
import hmac
import re
import secrets
from typing import Optional, Tuple

import database

ITERATIONS = 310_000  # Exceeds the 200,000 requirement


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """
    Hash a password using PBKDF2-HMAC-SHA256 with a 16-byte random salt.
    Returns (hex_hash, hex_salt).
    """
    if salt is None:
        salt = secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        ITERATIONS,
    ).hex()

    return password_hash, salt


def verify_password(password: str, saved_hash: str, salt: str) -> bool:
    """
    Verify password against saved PBKDF2 hash using constant-time comparison.
    """
    calculated_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(calculated_hash, saved_hash)


def validate_email(email: str) -> bool:
    """Validate standard email format."""
    if not email:
        return False
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()))


def register_user(email: str, password: str) -> Tuple[bool, str]:
    """
    Register a new user account with parameterized database query.
    Validates email format and minimum password length of 8.
    """
    clean_email = email.strip().lower()

    if not validate_email(clean_email):
        return False, "Enter a valid email address."

    if len(password) < 8:
        return False, "Password must contain at least 8 characters."

    pwd_hash, salt = hash_password(password)
    success = database.create_user(clean_email, pwd_hash, salt)
    if success:
        return True, "Account created successfully."
    return False, "This email is already registered."


def login_user(email: str, password: str) -> bool:
    """
    Verify login credentials for an email address.
    """
    clean_email = email.strip().lower()
    user = database.get_user_by_email(clean_email)
    if not user:
        return False

    # user dict: {"id": ..., "email": ..., "password_hash": ..., "salt": ...}
    return verify_password(password, user["password_hash"], user["salt"])
