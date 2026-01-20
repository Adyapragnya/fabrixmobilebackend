import os
import mimetypes
from pathlib import Path
from datetime import timedelta
from flask import request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from util import utcnow, new_id, norm

_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
_AUD_EXT = {".m4a", ".aac", ".mp3", ".wav", ".ogg"}
# If you ever record as .mp4 (AAC in mp4 container), then enable this:
# _AUD_EXT = {".m4a", ".aac", ".mp3", ".wav", ".ogg", ".mp4"}

_MAX_IMAGES = 3


def register_mobile_routes(app, workorders, users, require_auth):
    upload_root = Path(os.getenv("UPLOAD_ROOT", "./uploads")).resolve()
    wo_upload_root = upload_root / "workorders"
    wo_upload_root.mkdir(parents=True, exist_ok=True)

    max_upload_mb = int(os.getenv("MOBILE_MAX_UPLOAD_MB", "35"))
    app.config.setdefault("MAX_CONTENT_LENGTH", max_upload_mb * 1024 * 1024)

    def _role(u):
        return (u or {}).get("role") or ""

    def _is_admin(u):
        return _role(u) in ("SUPER_ADMIN", "ADMIN")

    def _can_access_wo(u, wo):
        if not u or not wo:
            return False
        if _is_admin(u):
            return True
        return u.get("_id") in (wo.get("assigned_team_ids") or [])

    def _work_public(d):
        return {
            "id": d.get("_id"),
            "wo_no": d.get("wo_no"),
            "customer_name": d.get("customer_name"),
            "phone": d.get("phone"),
            "address": d.get("address"),
            "status": d.get("status"),
            "schedule": d.get("schedule") or None,
            "location": d.get("location") or None,  # {lat,lng,label}
            "updated_at": d.get("updated_at").isoformat() if d.get("updated_at") else None,
        }

    @app.get("/mobile/my-workorders")
    @require_auth
    def my_workorders():
        u = request.user
        status_q = norm(request.args.get("status"))
        user_id = norm(request.args.get("user_id"))

        target_uid = u.get("_id")
        if user_id and _is_admin(u):
            target_uid = user_id

        base_and = [{"is_deleted": {"$ne": True}}]
        if status_q:
            statuses = [s.strip() for s in status_q.split(",") if s.strip()]
            base_and.append({"status": {"$in": statuses}} if len(statuses) > 1 else {"status": statuses[0]})

        if not _is_admin(u) or user_id:
            base_and.append({"assigned_team_ids": target_uid})

        filt = {"$and": base_and} if len(base_and) > 1 else base_and[0]
        cur = workorders.find(filt).sort("updated_at", -1).limit(500)
        return jsonify({"items": [_work_public(d) for d in cur]})

    def _save_file(file_storage, dest_dir: Path, kind: str):
        if not file_storage:
            return None
        filename = secure_filename(file_storage.filename or "")
        if not filename:
            guessed = mimetypes.guess_extension(file_storage.mimetype or "") or ""
            filename = f"{kind}{guessed or ''}"
        ext = Path(filename).suffix.lower()

        if kind == "image" and ext not in _IMG_EXT:
            raise ValueError(f"Invalid image type: {ext}")
        if kind == "voice" and ext not in _AUD_EXT:
            raise ValueError(f"Invalid audio type: {ext}")

        dest_dir.mkdir(parents=True, exist_ok=True)
        final_name = filename
        i = 2
        while (dest_dir / final_name).exists():
            stem = Path(filename).stem
            final_name = f"{stem}_{i}{ext}"
            i += 1

        out_path = dest_dir / final_name
        file_storage.save(out_path)
        mime = file_storage.mimetype or (mimetypes.guess_type(str(out_path))[0] or "application/octet-stream")
        size = out_path.stat().st_size
        url = f"/mobile/uploads/workorders/{dest_dir.parent.name}/{dest_dir.name}/{final_name}"
        return {"name": final_name, "url": url, "mime": mime, "size": int(size)}

    @app.get("/mobile/uploads/workorders/<wo_id>/<update_id>/<filename>")
    @require_auth
    def get_upload(wo_id, update_id, filename):
        u = request.user
        wo = workorders.find_one({"_id": wo_id, "is_deleted": {"$ne": True}})
        if not wo:
            return jsonify({"detail": "Not found"}), 404
        if not _can_access_wo(u, wo):
            return jsonify({"detail": "Forbidden"}), 403

        ok = False
        for up in (wo.get("work_updates") or []):
            if str(up.get("id") or "") != str(update_id):
                continue
            for im in (up.get("images") or []):
                if (im or {}).get("name") == filename:
                    ok = True
                    break
            v = up.get("voice") or {}
            if v.get("name") == filename:
                ok = True
            break
        if not ok:
            return jsonify({"detail": "Not found"}), 404

        dir_path = wo_upload_root / wo_id / update_id
        return send_from_directory(dir_path, filename, as_attachment=False)

    # ==========================================================
    # NEW: ACCEPTED -> IN_PROGRESS (used by dropdown)
    # ==========================================================
    @app.post("/mobile/workorders/<wo_id>/in-progress")
    @require_auth
    def mark_in_progress(wo_id):
        u = request.user
        wo = workorders.find_one({"_id": wo_id, "is_deleted": {"$ne": True}})
        if not wo:
            return jsonify({"detail": "Not found"}), 404
        if not _can_access_wo(u, wo):
            return jsonify({"detail": "Forbidden"}), 403

        cur_status = (norm(wo.get("status")) or "").upper()

        if cur_status == "COMPLETED":
            return jsonify({"detail": "Already completed"}), 400

        # Allowed transitions:
        # ACCEPTED -> IN_PROGRESS
        # IN_PROGRESS -> IN_PROGRESS (idempotent)
        if cur_status not in ("ACCEPTED", "IN_PROGRESS"):
            return jsonify({"detail": f"Cannot start work from status: {cur_status}"}), 400

        now = utcnow()
        hist = wo.get("history") or []

        if cur_status != "IN_PROGRESS":
            hist.append({
                "at": now.isoformat(),
                "by": u.get("_id"),
                "action": "MOBILE_START_WORK",
                "status": "IN_PROGRESS"
            })

            patch = {
                "status": "IN_PROGRESS",
                "in_progress_by": u.get("_id"),
                "in_progress_at": now,
                "history": hist,
                "updated_at": now,
            }
            workorders.update_one({"_id": wo_id}, {"$set": patch})

        return jsonify({"ok": True, "id": wo_id, "status": "IN_PROGRESS"})

    @app.post("/mobile/workorders/<wo_id>/submit")
    @require_auth
    def submit_work(wo_id):
        u = request.user
        wo = workorders.find_one({"_id": wo_id, "is_deleted": {"$ne": True}})
        if not wo:
            return jsonify({"detail": "Not found"}), 404
        if not _can_access_wo(u, wo):
            return jsonify({"detail": "Forbidden"}), 403

        note = norm(request.form.get("note"))
        status_in = norm(request.form.get("status"))
        target_status = (status_in or "IN_PROGRESS").upper()

        if target_status not in ("IN_PROGRESS", "COMPLETED"):
            return jsonify({"detail": "Invalid status. Use IN_PROGRESS or COMPLETED"}), 400

        cur_status = (wo.get("status") or "").upper()
        if cur_status == "COMPLETED":
            return jsonify({"detail": "Already completed"}), 400

        images = request.files.getlist("images") or []
        voice = request.files.get("voice")

        if len(images) > _MAX_IMAGES:
            return jsonify({"detail": f"max {_MAX_IMAGES} images"}), 400
        if not note and not images and not voice:
            return jsonify({"detail": "Provide note, images, or voice"}), 400

        update_id = new_id()
        update_dir = wo_upload_root / wo_id / update_id

        imgs_meta = []
        try:
            for f in images:
                if not f or not (f.filename or "").strip():
                    continue
                imgs_meta.append(_save_file(f, update_dir, "image"))
            voice_meta = None
            if voice and (voice.filename or "").strip():
                voice_meta = _save_file(voice, update_dir, "voice")
        except ValueError as ve:
            try:
                if update_dir.exists():
                    for p in update_dir.glob("*"):
                        p.unlink(missing_ok=True)
                    update_dir.rmdir()
            except Exception:
                pass
            return jsonify({"detail": str(ve)}), 400

        now = utcnow()
        updates = wo.get("work_updates") or []
        update_doc = {
            "id": update_id,
            "at": now.isoformat(),
            "by": u.get("_id"),
            "message": note or "",
            "images": [m for m in imgs_meta if m],
            "voice": voice_meta,
            "source": "MOBILE",
            "status": target_status,  # optional per-update status trace
        }
        updates.append(update_doc)

        hist = wo.get("history") or []
        hist.append({
            "at": now.isoformat(),
            "by": u.get("_id"),
            "action": "MOBILE_SUBMIT",
            "status": target_status
        })

        patch = {
            "work_updates": updates,
            "history": hist,
            "status": target_status,
            "updated_at": now,
        }

        if target_status == "COMPLETED":
            patch.update({
                "completed_by": u.get("_id"),
                "completed_at": now,
            })

        workorders.update_one({"_id": wo_id}, {"$set": patch})
        return jsonify({"ok": True, "update": update_doc, "status": target_status})

    @app.get("/mobile/achievement")
    @require_auth
    def achievement():
        u = request.user
        user_id = norm(request.args.get("user_id"))
        target_uid = u.get("_id")
        if user_id and _is_admin(u):
            target_uid = user_id

        now = utcnow()
        d7 = now - timedelta(days=7)
        d30 = now - timedelta(days=30)

        total_assigned = workorders.count_documents({"is_deleted": {"$ne": True}, "assigned_team_ids": target_uid})
        total_completed = workorders.count_documents({"is_deleted": {"$ne": True}, "completed_by": target_uid})
        completed_7d = workorders.count_documents({"is_deleted": {"$ne": True}, "completed_by": target_uid, "completed_at": {"$gte": d7}})
        completed_30d = workorders.count_documents({"is_deleted": {"$ne": True}, "completed_by": target_uid, "completed_at": {"$gte": d30}})
        active = workorders.count_documents({"is_deleted": {"$ne": True}, "assigned_team_ids": target_uid, "status": {"$in": ["ASSIGNED", "ACCEPTED", "IN_PROGRESS"]}})

        cur = workorders.find({"is_deleted": {"$ne": True}, "completed_by": target_uid}).sort("completed_at", -1).limit(60)
        recent = []
        for d in cur:
            recent.append({
                "id": d.get("_id"),
                "wo_no": d.get("wo_no"),
                "customer_name": d.get("customer_name"),
                "completed_at": d.get("completed_at").isoformat() if d.get("completed_at") else None,
                "location": d.get("location") or None,
                "status": d.get("status"),
            })

        badges = []
        if total_completed >= 1:
            badges.append({"key": "first", "title": "First Finish", "hint": "Completed your first work"})
        if total_completed >= 10:
            badges.append({"key": "ten", "title": "10 Jobs", "hint": "Completed 10 works"})
        if completed_7d >= 5:
            badges.append({"key": "week5", "title": "On Fire", "hint": "5 works in last 7 days"})

        return jsonify({
            "user_id": target_uid,
            "totals": {
                "assigned": total_assigned,
                "completed": total_completed,
                "active": active,
                "completed_7d": completed_7d,
                "completed_30d": completed_30d
            },
            "badges": badges,
            "timeline": recent,
        })