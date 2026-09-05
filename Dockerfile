FROM python:3.12-slim

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + static + game bundle
COPY app ./app
COPY static ./static
COPY game ./game

# Persistent data volume (users DB + save slots)
VOLUME ["/app/data"]
ENV DATA_DIR=/app/data

EXPOSE 8000

CMD ["python", "-m", "app.main"]
