FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ফিক্স: পুরনো instance kill করে নতুন চালু করা
CMD pkill -f "python bot.py" || true && pkill -f "gunicorn" || true && \
    gunicorn bot:app_flask --bind 0.0.0.0:8081 --workers 2 --threads 2 & \
    python bot.py
