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
CMD ["python", "-m", "app"]
