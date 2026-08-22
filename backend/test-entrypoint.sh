#!/bin/sh
set -eu

alembic upgrade head
alembic downgrade base
alembic upgrade head
python -m app.db.seed
pytest
