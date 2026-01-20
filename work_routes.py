from flask import request, jsonify
from util import utcnow

def register_work_routes(app, workorders, require_auth):
    @app.post("/workorders/<wo_id>/accept")
    @require_auth
    def accept_work(wo_id):
        u = request.user
        d = workorders.find_one({"_id": wo_id, "is_deleted": {"$ne": True}})
        if not d:
            return jsonify({"detail": "Not found"}), 404
        if u["_id"] not in (d.get("assigned_team_ids") or []):
            return jsonify({"detail": "Forbidden"}), 403

        now = utcnow()
        status = d.get("status") or "DRAFT"
        if status not in ("ASSIGNED", "DRAFT"):
            return jsonify({"detail": "Invalid state"}), 409

        hist = d.get("history") or []
        hist.append({"at": now.isoformat(), "by": u["_id"], "action": "ACCEPT", "status": "ACCEPTED"})

        workorders.update_one(
            {"_id": wo_id},
            {"$set": {"status": "ACCEPTED", "accepted_by": u["_id"], "accepted_at": now, "history": hist, "updated_at": now}},
        )
        return jsonify({"ok": True})
