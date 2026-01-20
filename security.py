import os
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone

def _now():
    return datetime.now(timezone.utc)

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False

def create_access_token(user_id: str, username: str, role: str, minutes: int) -> str:
    secret = os.getenv("ACCESS_TOKEN_SECRET", "change_me_access_secret_please")
    exp = _now() + timedelta(minutes=minutes)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "type": "access",
        "iat": int(_now().timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")

def create_refresh_token(user_id: str, days: int) -> str:
    secret = os.getenv("REFRESH_TOKEN_SECRET", "change_me_refresh_secret_please")
    exp = _now() + timedelta(days=days)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": int(_now().timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")

def decode_access_token(token: str):
    secret = os.getenv("ACCESS_TOKEN_SECRET", "change_me_access_secret_please")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        if payload.get("type") != "access":
            return None
        return payload
    except Exception:
        return None
