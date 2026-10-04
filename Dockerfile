ARG BASE_IMAGE=southamerica-east1-docker.pkg.dev/idesp-473218/idesp-base-images/python-runtime:python3.12-slim
FROM ${BASE_IMAGE}

USER root

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --chown=10001:10001 .build/venv/ /opt/venv/
COPY --chown=10001:10001 app/ /app/app/
COPY --chown=10001:10001 alembic/ /app/alembic/
COPY --chown=10001:10001 alembic.ini requirements.txt /app/

RUN python -c 'import sys; assert sys.version_info[:2] == (3, 12); assert sys.prefix == "/opt/venv"' \
    && mkdir -p /app/uploads/_chunks \
    && chown -R 10001:10001 /app/uploads \
    && chown 10001:10001 /app

USER 10001:10001

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
