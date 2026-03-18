FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# পুরনো প্রসেস কিল করে নতুন চালু করা
CMD pkill -f "python bot.py" ; pkill -f "gunicorn" ; sleep 2 ; \
    gunicorn bot:app_flask --bind 0.0.0.0:8081 --workers 1 --threads 2 & \
    python bot.py
