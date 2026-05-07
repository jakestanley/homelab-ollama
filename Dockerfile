FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN python3 -m venv .venv && .venv/bin/pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates/ ./templates/

CMD [".venv/bin/python", "app.py"]
