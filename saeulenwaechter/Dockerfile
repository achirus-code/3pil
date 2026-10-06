# Säulenwächter – Home-Assistant-App. BUILD_FROM kommt aus build.yaml (python:3.12-slim je Architektur).
ARG BUILD_FROM=python:3.12-slim
FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SW_DATA_DIR=/data

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

EXPOSE 8099
# Home Assistant zeigt „Startet“, bis der erste Check passt, und startet die App bei Hängern neu
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/api/health', timeout=4)"
CMD ["python", "-m", "app"]
