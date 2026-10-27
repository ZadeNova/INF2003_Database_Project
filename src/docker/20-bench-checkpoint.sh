#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -v owner="$APP_OWNER_USER" <<'SQL'
GRANT pg_checkpoint TO :"owner";
SQL
