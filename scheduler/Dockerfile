FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY scheduler/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY scheduler/ .

CMD ["celery", "-A", "celery_app", "worker", "--concurrency=4", "--loglevel=info"]