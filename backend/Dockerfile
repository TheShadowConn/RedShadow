FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    XDG_CACHE_HOME=/tmp/cache
# procps: pgrep for the celery beat healthcheck. pango, harfbuzz and fonts: WeasyPrint renders the PDF reports.
RUN apt-get update \
    && apt-get install -y --no-install-recommends procps libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fontconfig fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 app \
    && useradd -u 10001 -g app -M -s /usr/sbin/nologin app \
    && mkdir -p /data/media /data/beat /data/staging \
    && chown -R app:app /data
WORKDIR /app
COPY requirements.txt requirements-dev.txt ./

FROM base AS test
RUN pip install -r requirements-dev.txt
COPY . .
USER app
CMD ["pytest", "-q"]

FROM base AS prod
RUN pip install -r requirements.txt
COPY . .
USER app
EXPOSE 8000
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-3} --worker-tmp-dir /dev/shm --timeout ${GUNICORN_TIMEOUT:-600} --access-logfile -"]
