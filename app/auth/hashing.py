# ABOUTME: bcrypt password hashing and verification using the bcrypt library directly.
# ABOUTME: Using bcrypt directly avoids passlib's version-detection issues with bcrypt 4.x.
from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())
