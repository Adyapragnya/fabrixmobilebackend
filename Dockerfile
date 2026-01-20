FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir gunicorn

COPY . /app

# uploads folder will be mounted as volume; ensure it exists
RUN mkdir -p /app/uploads

EXPOSE 8100

# Gunicorn imports "app" variable from app.py (your file has: app = Flask(__name__))
CMD ["gunicorn", "-w", "3", "-k", "gthread", "--threads", "8", "-b", "0.0.0.0:8100", "--timeout", "120", "app:app"]
