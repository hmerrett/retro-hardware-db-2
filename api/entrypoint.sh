#!/bin/sh
# Bring the schema to head, then start the app.
#
# Handles three cases safely:
#   * fresh DB            -> alembic upgrade creates the tables
#   * already on Alembic  -> alembic upgrade applies any new migrations
#   * pre-Alembic DB      -> tables exist from the old create_all but there's no
#                            alembic_version; stamp the baseline first so upgrade
#                            doesn't try to recreate them.
set -e

DECIDE=$(python - <<'PY'
from sqlalchemy import inspect
from app.db import engine
insp = inspect(engine)
if insp.has_table("alembic_version"):
    print("upgrade")
elif insp.has_table("computers"):
    print("stamp")
else:
    print("upgrade")
PY
)

if [ "$DECIDE" = "stamp" ]; then
    echo "entrypoint: pre-Alembic database detected, stamping baseline."
    alembic stamp head
fi

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
