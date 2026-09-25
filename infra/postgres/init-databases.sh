#!/bin/sh
# Runs once, on first init of an empty postgres data volume, via
# /docker-entrypoint-initdb.d/. POSTGRES_DB (cq_dev) is already created by
# the postgres image itself; this script adds the two extra databases the
# local stack needs: cq_test (app test DB) and temporal (Temporal server's
# own DB, per CQ-003 spec Decision: Temporal reuses this postgres service).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE cq_test OWNER "$POSTGRES_USER";
    CREATE DATABASE temporal OWNER "$POSTGRES_USER";
EOSQL
