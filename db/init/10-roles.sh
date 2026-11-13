#!/bin/sh
# Runs once, on an empty data directory, as the bootstrap superuser (redshadow_admin).
set -eu

OWNER_PW="$(cat /run/secrets/db_owner_password)"
APP_PW="$(cat /run/secrets/db_app_password)"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
     -v owner_pw="$OWNER_PW" -v app_pw="$APP_PW" <<'SQL'
CREATE ROLE redshadow_owner LOGIN PASSWORD :'owner_pw'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE redshadow_app LOGIN PASSWORD :'app_pw'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE DATABASE redshadow OWNER redshadow_owner;
REVOKE ALL ON DATABASE redshadow FROM PUBLIC;
GRANT CONNECT ON DATABASE redshadow TO redshadow_app;
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname redshadow \
     -f /opt/redshadow/sql/harden.sql
