#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 \
     -v dbm_monitoring_password="${DBM_MONITORING_PASSWORD:-datadog}" \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -f /docker-entrypoint-initdb.d/init.sql.template
