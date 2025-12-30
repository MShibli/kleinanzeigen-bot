FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# System dependencies (für bs4, requests etc.)
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "ebAlert/main.py"]
