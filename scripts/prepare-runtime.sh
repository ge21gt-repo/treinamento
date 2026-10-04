#!/bin/sh
set -eu

export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1

if ! test -s requirements.txt; then
    echo "requirements.txt ausente ou vazio; execute na raiz do projeto." >&2
    exit 1
fi
if test -e .build/venv; then
    echo ".build/venv ja existe; use um checkout limpo para reconstruir as dependencias." >&2
    exit 1
fi
python -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version'

# O caminho absoluto deve ser o mesmo no agente e no runtime (shebangs).
python -m venv /opt/venv
/opt/venv/bin/python -m pip install --no-cache-dir -r requirements.txt
/opt/venv/bin/python -m pip check

DATABASE_URL='postgresql+asyncpg://build:build@localhost:5432/build' \
SECRET_KEY='build-import-check-not-for-deployment' \
STORAGE_BACKEND=local \
    /opt/venv/bin/python -c 'from app.main import app; print(f"{len(app.routes)} routes loaded")'

/opt/venv/bin/python -m pip uninstall --yes pip
mkdir -p .build
cp -a /opt/venv .build/venv
