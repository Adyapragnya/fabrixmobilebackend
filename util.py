import hashlib
import secrets
from datetime import datetime, timezone

def utcnow():
    return datetime.now(timezone.utc)

def new_id():
    return secrets.token_urlsafe(12).replace("-", "").replace("_", "")

def mac_hash(mac: str):
    if not mac:
        return None
    m = str(mac).strip().lower()
    if not m:
        return None
    return hashlib.sha256(m.encode("utf-8")).hexdigest()

def norm(s):
    return (s or "").strip()
