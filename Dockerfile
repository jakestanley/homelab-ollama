FROM ollama/ollama

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates/ ./templates/
COPY scripts/up.sh ./scripts/up.sh
RUN chmod +x scripts/up.sh

CMD ["scripts/up.sh"]
