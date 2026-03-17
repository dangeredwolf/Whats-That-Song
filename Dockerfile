FROM python:3.13-alpine

# Runtime system deps
RUN apk add --no-cache \
    ffmpeg \
    git \
    libsodium \
    opus

# Build-time deps needed to compile PyNaCl and other native extensions
RUN apk add --no-cache --virtual .build-deps \
    gcc \
    musl-dev \
    libffi-dev \
    libsodium-dev

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

COPY *.py .

CMD ["python", "bot.py"]
