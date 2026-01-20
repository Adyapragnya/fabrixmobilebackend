# FabriX Mobile Backend (separate service)

This is a **standalone** Flask backend intended for mobile users (and optionally admins),
while sharing the **same MongoDB** with your desktop backend.

## Dev run (Windows PowerShell)
```powershell
cd mobile-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python app.py
```

It will run on:
- http://127.0.0.1:8100  (default)

## Production run (Linux)
```bash
pip install -r requirements.txt
gunicorn -w 2 -k gthread -b 0.0.0.0:8100 app:app
```

## Endpoints
Auth:
- POST /auth/login
- GET  /auth/me
- POST /auth/logout

Work:
- GET  /mobile/my-workorders?status=ASSIGNED,ACCEPTED
- POST /workorders/<wo_id>/accept
- POST /mobile/workorders/<wo_id>/submit     (multipart: images[] up to 3, voice, note)
- GET  /mobile/achievement
- GET  /mobile/uploads/workorders/<wo_id>/<update_id>/<filename>

## Important
- This service does NOT create workorders. Desktop remains the source of creation/assignment.
- Work lifecycle fields match desktop: status, accepted_by/at, completed_by/at, history, work_updates.
