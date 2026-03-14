# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WDM_LOG_LEVEL=0 \
    CHROME_BINARY=/usr/bin/chromium \
    CHROMEDRIVER_BINARY=/usr/bin/chromedriver

# Install Chromium & fonts for Selenium runs
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       chromium \
       chromium-driver \
       fonts-liberation \
       tzdata \
       xvfb \
       x11vnc \
       fluxbox \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

# Default to headless execution inside containers
ENV TT_HEADLESS=1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["--weight", "0.65"]
