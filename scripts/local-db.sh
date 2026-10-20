#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_ROOT="$PROJECT_ROOT/.local/postgres"
DATA_DIR="$LOCAL_ROOT/data"
SOCKET_DIR="/tmp/mirai-path-postgres"
LOG_FILE="$LOCAL_ROOT/postgres.log"
DB_PORT="${PGPORT:-5433}"
DB_NAME="apprentissage_langue"
DB_USER="apprentissage_app"
DB_PASSWORD="apprentissage_dev"

resolve_postgres_bin() {
  local candidate

  if [[ -n "${POSTGRES_BIN:-}" ]]; then
    candidate="$POSTGRES_BIN"
  elif command -v brew >/dev/null 2>&1; then
    candidate="$(brew --prefix postgresql@15 2>/dev/null)/bin"
  else
    candidate="$(dirname "$(command -v postgres 2>/dev/null || true)")"
  fi

  if [[ ! -x "$candidate/postgres" || ! -x "$candidate/initdb" ]]; then
    echo "PostgreSQL server binaries not found. Install them with: brew install postgresql@15" >&2
    exit 1
  fi

  POSTGRES_BIN="$candidate"
}

is_running() {
  "$POSTGRES_BIN/pg_ctl" -D "$DATA_DIR" status >/dev/null 2>&1
}

start_database() {
  mkdir -p "$SOCKET_DIR"

  if is_running; then
    echo "PostgreSQL is already running on port $DB_PORT."
    return
  fi

  "$POSTGRES_BIN/pg_ctl" -D "$DATA_DIR" -l "$LOG_FILE" -o "-p $DB_PORT -h 127.0.0.1 -k $SOCKET_DIR" start
}

setup_database() {
  mkdir -p "$LOCAL_ROOT" "$SOCKET_DIR"

  if [[ ! -f "$DATA_DIR/PG_VERSION" ]]; then
    local password_file
    password_file="$(mktemp "$LOCAL_ROOT/initdb-password.XXXXXX")"
    chmod 600 "$password_file"
    printf '%s\n' "mirai_local_admin" >"$password_file"
    if ! "$POSTGRES_BIN/initdb" \
      -D "$DATA_DIR" \
      --username=postgres \
      --pwfile="$password_file" \
      --auth-local=trust \
      --auth-host=scram-sha-256 \
      --encoding=UTF8; then
      rm -f "$password_file"
      exit 1
    fi
    rm -f "$password_file"
  fi

  start_database

  if [[ "$("$POSTGRES_BIN/psql" -h "$SOCKET_DIR" -p "$DB_PORT" -U postgres -d postgres -Atqc "SELECT 1 FROM pg_roles WHERE rolname = '$DB_USER'")" != "1" ]]; then
    "$POSTGRES_BIN/psql" -h "$SOCKET_DIR" -p "$DB_PORT" -U postgres -d postgres \
      -v ON_ERROR_STOP=1 \
      -c "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD'"
  else
    "$POSTGRES_BIN/psql" -h "$SOCKET_DIR" -p "$DB_PORT" -U postgres -d postgres \
      -v ON_ERROR_STOP=1 \
      -c "ALTER ROLE $DB_USER WITH LOGIN PASSWORD '$DB_PASSWORD'" >/dev/null
  fi

  if [[ "$("$POSTGRES_BIN/psql" -h "$SOCKET_DIR" -p "$DB_PORT" -U postgres -d postgres -Atqc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'")" != "1" ]]; then
    "$POSTGRES_BIN/createdb" -h "$SOCKET_DIR" -p "$DB_PORT" -U postgres -O "$DB_USER" "$DB_NAME"
  fi

  echo "Local database ready: postgresql://$DB_USER@localhost:$DB_PORT/$DB_NAME"
}

stop_database() {
  if [[ ! -f "$DATA_DIR/PG_VERSION" ]]; then
    echo "Local database has not been initialized."
    return
  fi

  if is_running; then
    "$POSTGRES_BIN/pg_ctl" -D "$DATA_DIR" stop -m fast
  else
    echo "PostgreSQL is already stopped."
  fi
}

database_status() {
  if [[ ! -f "$DATA_DIR/PG_VERSION" ]]; then
    echo "Local database has not been initialized. Run: ./scripts/local-db.sh setup"
    exit 1
  fi

  "$POSTGRES_BIN/pg_ctl" -D "$DATA_DIR" status
}

resolve_postgres_bin

case "${1:-}" in
  setup)
    setup_database
    ;;
  start)
    if [[ ! -f "$DATA_DIR/PG_VERSION" ]]; then
      echo "Local database has not been initialized. Run: ./scripts/local-db.sh setup" >&2
      exit 1
    fi
    start_database
    ;;
  stop)
    stop_database
    ;;
  status)
    database_status
    ;;
  *)
    echo "Usage: $0 {setup|start|stop|status}" >&2
    exit 1
    ;;
esac
