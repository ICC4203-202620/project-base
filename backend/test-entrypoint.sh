#!/bin/sh
set -eu

alembic upgrade head
python -m app.db.seed
pytest
