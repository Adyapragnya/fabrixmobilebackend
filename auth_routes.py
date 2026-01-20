import os
from datetime import datetime
from flask import request, jsonify
from functools import wraps

from security import verify_password, create_access_token, create_refresh_token, decode_access_token
from util import utcnow, mac_hash, norm

ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "30"))
SUPER_USER_USERNAME = os.getenv("SUPER_USER_USERNAME", "Adyapragnya").strip()

RELEASE_DEVICE_ON_LOGOUT = os.getenv("RELEASE_DEVICE_ON_LOGOUT", "1").strip() not in ("0", "false", "False")

def subscription_allows(u: dict) -> bool:
    if not u:
        return False
    now = utcnow()
    start = u.get("subscription_start")
    end = u.get("subscription_end")
    try:
        if start and isinstance(start, datetime) and now < start:
            return False
        if end and isinstance(end, datetime) and now > end:
            return False
    except Exception:
        pass
    return True

def is_super_user(u: dict) -> bool:
    if not u:
        return False
    if u.get("role") == "SUPER_ADMIN":
        return True
    return (u.get("username") or "").strip().lower() == SUPER_USER_USERNAME.lower()

def bearer_token():
    h = request.headers.get("Authorization") or ""
    if h.lower().startswith("bearer "):
        return h.split(" ", 1)[1].strip()
    return ""

def require_auth(users):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            token = bearer_token()
            payload = decode_access_token(token)
            if not payload:
                return jsonify({"detail": "Invalid token"}), 401
            uid = payload.get("sub")
            u = users.find_one({"_id": uid, "is_deleted": {"$ne": True}})
            if not u or not u.get("is_active", True):
                return jsonify({"detail": "User disabled"}), 403
            request.user = u
            return fn(*args, **kwargs)
        return wrapper
    return deco

def register_auth_routes(app, users):
    @app.post("/auth/login")
    def login():
        data = request.get_json(force=True) or {}
        username = norm(data.get("username"))
        password = data.get("password") or ""
        remember_me = bool(data.get("remember_me", True))

        device_id = norm(data.get("device_id"))
        mac_address = norm(data.get("mac_address"))

        u = users.find_one({"username": username, "is_deleted": {"$ne": True}})
        if not u or not u.get("is_active", True):
            return jsonify({"detail": "Invalid credentials"}), 401
        if u.get("is_locked", False):
            return jsonify({"detail": "Account locked"}), 403
        if not subscription_allows(u):
            return jsonify({"detail": "Subscription inactive/expired"}), 403
        if not verify_password(password, u.get("password_hash", "")):
            return jsonify({"detail": "Invalid credentials"}), 401

        if not is_super_user(u):
            if not device_id:
                return jsonify({"detail": "device_id required for this account"}), 400

            existing_device = norm(u.get("active_device_id"))
            if existing_device and existing_device != device_id:
                return jsonify({"detail": "This account is already active on another system. Ask SUPER_ADMIN to unlink the device."}), 409

            patch = {
                "active_device_id": device_id,
                "active_device_last_login": utcnow(),
                "updated_at": utcnow(),
            }
            mh = mac_hash(mac_address)
            if mh:
                patch["active_device_mac_hash"] = mh
            users.update_one({"_id": u["_id"]}, {"$set": patch})
            u = users.find_one({"_id": u["_id"]})

        access = create_access_token(u["_id"], u["username"], u["role"], ACCESS_TOKEN_MINUTES)
        refresh = create_refresh_token(u["_id"], REFRESH_TOKEN_DAYS) if remember_me else None

        return jsonify({
            "user": {
                "id": u["_id"],
                "username": u["username"],
                "role": u["role"],
                "user_type": u.get("user_type") or ("MOBILE_USER" if u.get("role") == "MOBILE_USER" else "ADMIN"),
                "full_name": u.get("full_name"),
                "phone": u.get("phone"),
                "allowed_modules": u.get("allowed_modules") or [],
                "subscription_start": u.get("subscription_start").isoformat() if u.get("subscription_start") else None,
                "subscription_end": u.get("subscription_end").isoformat() if u.get("subscription_end") else None,
            },
            "access_token": access,
            "refresh_token": refresh,
        })

    @app.get("/auth/me")
    @require_auth(users)
    def me():
        u = request.user
        return jsonify({
            "user": {
                "id": u["_id"],
                "username": u["username"],
                "role": u["role"],
                "user_type": u.get("user_type"),
                "full_name": u.get("full_name"),
                "phone": u.get("phone"),
                "allowed_modules": u.get("allowed_modules") or [],
                "subscription_start": u.get("subscription_start").isoformat() if u.get("subscription_start") else None,
                "subscription_end": u.get("subscription_end").isoformat() if u.get("subscription_end") else None,
            }
        })

    @app.post("/auth/logout")
    @require_auth(users)
    def logout():
        u = request.user
        data = request.get_json(force=True) or {}
        device_id = norm(data.get("device_id"))

        if RELEASE_DEVICE_ON_LOGOUT and u.get("role") != "SUPER_ADMIN":
            if device_id and norm(u.get("active_device_id")) == device_id:
                users.update_one(
                    {"_id": u["_id"]},
                    {"$set": {"active_device_id": None, "active_device_mac_hash": None, "updated_at": utcnow()}},
                )
        return jsonify({"ok": True})
