FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    gcc \
    pkg-config \
    libffi-dev \
    libsodium-dev \
    libopus-dev \
    libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

CMD ["python", "bot.py"]
