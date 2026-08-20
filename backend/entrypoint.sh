#!/bin/sh
set -eu
alembic upgrade head
python -m app.db.seed
if [ "${LOCAL_TLS:-false}" = "true" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --ssl-certfile "${TLS_CERTFILE:-/certs/local.pem}" --ssl-keyfile "${TLS_KEYFILE:-/certs/local-key.pem}"
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
