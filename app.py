import os
from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

from db import get_db
from auth_routes import register_auth_routes, require_auth as require_auth_factory
from work_routes import register_work_routes
from mobile_routes import register_mobile_routes

load_dotenv()

app = Flask(__name__)

_allow = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
allow_origins = "*" if _allow in ("*", "") else [x.strip() for x in _allow.split(",") if x.strip()]
CORS(app, resources={r"/*": {"origins": allow_origins}})

db = get_db()
users = db["users"]
workorders = db["workorders"]

require_auth = require_auth_factory(users)

@app.get("/")
def health():
    return jsonify({"ok": True, "service": "fabrix-mobile-backend"})

register_auth_routes(app, users)
register_work_routes(app, workorders, require_auth)
register_mobile_routes(app, workorders, users, require_auth)

if __name__ == "__main__":
    port = int(os.getenv("MOBILE_BACKEND_PORT", "8100"))
    app.run(host="0.0.0.0", port=port, debug=True)
