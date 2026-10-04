ARG BASE_IMAGE=python:3.12-slim-trixie
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip check

COPY --chown=10001:10001 app/ /app/app/
COPY --chown=10001:10001 alembic/ /app/alembic/
COPY --chown=10001:10001 alembic.ini /app/

RUN python -c 'import sys; assert sys.version_info[:2] == (3, 12)' \
    && mkdir -p /app/uploads/_chunks \
    && chown -R 10001:10001 /app/uploads \
    && chown 10001:10001 /app

USER 10001:10001

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
