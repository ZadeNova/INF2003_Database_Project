#!/bin/sh
set -eu
# Two application roles (AGENTS.md rule 5), created once on an empty data volume by the bootstrap superuser,
# whose password no application container receives.
#   owner:   owns the database; runs migrations, the importer and pytest (which creates test databases)
#   runtime: used by web; can read and write rows, never change the schema
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v db="$APP_DB_NAME" -v owner="$APP_OWNER_USER" -v owner_password="$APP_OWNER_PASSWORD" \
  -v runtime="$APP_RUNTIME_USER" -v runtime_password="$APP_RUNTIME_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEROLE CREATEDB PASSWORD %L', :'owner', :'owner_password') \gexec
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB PASSWORD %L', :'runtime', :'runtime_password') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'db', :'owner') \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'db') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db', :'runtime') \gexec
SQL
# Tables and sequences the owner creates later (every migration) are covered by the default privileges.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$APP_DB_NAME" \
  -v owner="$APP_OWNER_USER" -v runtime="$APP_RUNTIME_USER" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"runtime";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"runtime";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO :"runtime";
SQL
