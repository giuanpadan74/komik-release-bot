FROM python:3.12-slim

# Install cron
RUN apt-get update && apt-get install -y --no-install-recommends cron && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scraper.py .
COPY calendario.json .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ENV BOT_TOKEN=""
ENV CHAT_ID=""
ENV TOPIC_ID=""

# Crontab: ogni lunedì alle 10:00 UTC
RUN echo "0 10 * * 1 cd /app && /usr/local/bin/python /app/scraper.py >> /var/log/komik.log 2>&1" > /etc/cron.d/komik && \
    chmod 0644 /etc/cron.d/komik && \
    crontab /etc/cron.d/komik

ENTRYPOINT ["/app/entrypoint.sh"]
