# ── Florae · Plant Tracker ── Immagine Docker ufficiale ──
FROM python:3.11-slim

# Evita file .pyc e buffer output (log visibili nei container)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_DEBUG=0

WORKDIR /app

# 1) Dipendenze prima del codice: layer in cache quando cambia solo il sorgente
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Codice applicativo
COPY app.py list_models.py ./
COPY templates ./templates
COPY static ./static

# 3) Cartelle dati: uploads vuota + database persistente
RUN mkdir -p static/uploads instance

# Il database SQLite vive qui → montalo come volume per non perderlo
VOLUME ["/app/instance"]

EXPOSE 5001

CMD ["python", "app.py"]
