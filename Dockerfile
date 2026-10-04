ARG BASE_IMAGE=southamerica-east1-docker.pkg.dev/idesp-473218/idesp-base-images/python-runtime:python3.12-slim
FROM python:3.12-slim-trixie AS dependencies

WORKDIR /dependencies
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --target /opt/python -r requirements.txt \
    && PYTHONPATH=/opt/python python -m pip check

FROM ${BASE_IMAGE}

USER root

ENV PYTHONPATH=/opt/python \
    PATH="/opt/python/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=dependencies /opt/python/ /opt/python/
COPY --chown=10001:10001 app/ /app/app/
COPY --chown=10001:10001 alembic/ /app/alembic/
COPY --chown=10001:10001 alembic.ini requirements.txt /app/

RUN python -c 'import sys; assert sys.version_info[:2] == (3, 12)' \
    && mkdir -p /app/uploads/_chunks \
    && chown -R 10001:10001 /app/uploads \
    && chown 10001:10001 /app

USER 10001:10001

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
