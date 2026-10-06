# Säulenwächter – Home-Assistant-App.
# Das Basisimage steht bewusst fest hier (nicht über BUILD_FROM): das Standard-Image des Supervisors
# (ghcr.io/home-assistant/base) enthält kein Python. Die Plattform (amd64/aarch64) wählt der Supervisor per --platform.
FROM docker.io/library/python:3.12-slim

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
