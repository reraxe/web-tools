#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

CONFIRMATION_PHRASE="RUN PHASE 2 PREPROD GATE"
TEMP_PORT="${DEX_PREPROD_PORT:-18082}"
TEMP_NAME=""
TEMP_STARTED=0
GATE_PASSED=0
COPY_STORAGE=""
AUDIT_DIR=""
LIVE_CONTAINER_ID=""
LIVE_CONTAINER_IMAGE_ID=""

log() {
  printf '[phase2-gate] %s\n' "$*"
}

die() {
  printf '[phase2-gate] ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  local exit_code=$?
  local final_code=$exit_code
  trap - EXIT INT TERM
  set +e

  if [[ "$TEMP_STARTED" -eq 1 && "$TEMP_NAME" == dex-v21-preprod-* ]]; then
    docker rm -f "$TEMP_NAME" >/dev/null 2>&1
    TEMP_STARTED=0
  fi

  if [[ -n "$LIVE_CONTAINER_ID" ]]; then
    current_live_id="$(docker compose ps -q dex 2>/dev/null)"
    current_live_image_id=""
    current_live_running="false"
    if [[ -n "$current_live_id" ]]; then
      current_live_image_id="$(docker inspect --format '{{.Image}}' "$current_live_id" 2>/dev/null)"
      current_live_running="$(docker inspect --format '{{.State.Running}}' "$current_live_id" 2>/dev/null)"
    fi
    if [[ "$current_live_id" != "$LIVE_CONTAINER_ID" ||
          "$current_live_image_id" != "$LIVE_CONTAINER_IMAGE_ID" ||
          "$current_live_running" != "true" ]]; then
      printf '[phase2-gate] ERROR: live dex service identity/state changed during the gate.\n' >&2
      final_code=1
    fi
  fi

  if [[ "$final_code" -eq 0 && "$GATE_PASSED" -eq 1 ]]; then
    printf '\nPHASE 2 PRE-PRODUCTION GATE: PASS\n'
  else
    printf '\nPHASE 2 PRE-PRODUCTION GATE: FAIL\n' >&2
    final_code=1
  fi
  [[ -n "$COPY_STORAGE" ]] && printf 'Retained copied storage: %s\n' "$COPY_STORAGE"
  [[ -n "$AUDIT_DIR" ]] && printf 'Retained audit files: %s\n' "$AUDIT_DIR"
  exit "$final_code"
}

trap cleanup EXIT
trap 'exit 130' INT TERM

for command_name in awk docker curl cp date grep mkdir mv sed sleep ss tee wc; do
  command -v "$command_name" >/dev/null 2>&1 \
    || die "required command not found: $command_name"
done
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is unavailable"

[[ -t 0 ]] || die "an interactive terminal is required for operator confirmation"
printf 'This gate builds the configured image and tests only a copied database.\n'
printf 'It will not stop, restart, or mount the live DEX container storage into the test app.\n'
printf 'Type exactly: %s\n> ' "$CONFIRMATION_PHRASE"
read -r operator_confirmation
[[ "$operator_confirmation" == "$CONFIRMATION_PHRASE" ]] \
  || die "operator confirmation did not match"

DEX_ROOT="$(pwd -P)"
[[ -f "$DEX_ROOT/compose.yaml" ]] || die "run this script from the DEX repository root"
[[ -f "$DEX_ROOT/Dockerfile" ]] || die "Dockerfile not found in repository root"

mapfile -t compose_services < <(docker compose config --services)
printf '%s\n' "${compose_services[@]}" | grep -Fxq dex \
  || die "Compose service 'dex' is not present"

mapfile -t resolved_images < <(docker compose config --images)
[[ "${#resolved_images[@]}" -eq 1 ]] \
  || die "expected exactly one resolved Compose image, found ${#resolved_images[@]}"
RESOLVED_IMAGE="${resolved_images[0]}"
[[ -n "$RESOLVED_IMAGE" ]] || die "Compose image resolved to an empty value"
log "resolved Compose image: $RESOLVED_IMAGE"

LIVE_CONTAINER_ID="$(docker compose ps -q dex)"
[[ -n "$LIVE_CONTAINER_ID" ]] || die "live Compose dex container is not running"
[[ "$(docker inspect --format '{{.State.Running}}' "$LIVE_CONTAINER_ID")" == "true" ]] \
  || die "live Compose dex container is not in running state"
LIVE_CONTAINER_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER_ID")"

LIVE_STORAGE="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' "$LIVE_CONTAINER_ID")"
[[ -n "$LIVE_STORAGE" && -d "$LIVE_STORAGE" ]] \
  || die "could not resolve the live /data bind mount"
[[ -f "$LIVE_STORAGE/dex.db" ]] || die "live SQLite database not found at $LIVE_STORAGE/dex.db"

case "$TEMP_PORT" in
  ''|*[!0-9]*) die "DEX_PREPROD_PORT must be numeric" ;;
esac
(( TEMP_PORT >= 1024 && TEMP_PORT <= 65535 )) \
  || die "temporary port must be between 1024 and 65535"
[[ "$TEMP_PORT" != "8080" && "$TEMP_PORT" != "8082" ]] \
  || die "temporary port may not use a known production/application port"
if ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)$TEMP_PORT$"; then
  die "temporary port $TEMP_PORT is already in use"
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
COPY_STORAGE="$DEX_ROOT/preprod-copies/storage-v2.0-test-$STAMP"
AUDIT_DIR="$DEX_ROOT/preprod-copies/audit-$STAMP"
TEMP_NAME="dex-v21-preprod-$STAMP"

[[ ! -e "$COPY_STORAGE" && ! -e "$AUDIT_DIR" ]] \
  || die "timestamped pre-production paths already exist"
case "$COPY_STORAGE" in
  "$LIVE_STORAGE"|"$LIVE_STORAGE"/*) die "copied storage resolved inside live storage" ;;
esac
mkdir -p "$COPY_STORAGE" "$AUDIT_DIR"

log "building $RESOLVED_IMAGE without recreating the live service"
docker compose build --pull dex

mapfile -t post_build_images < <(docker compose config --images)
[[ "${#post_build_images[@]}" -eq 1 && "${post_build_images[0]}" == "$RESOLVED_IMAGE" ]] \
  || die "resolved Compose image changed during the build"
BUILT_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$RESOLVED_IMAGE")"
[[ -n "$BUILT_IMAGE_ID" ]] || die "built image ID could not be resolved"

docker run --rm --entrypoint sh "$RESOLVED_IMAGE" -c \
  'cd /app && test -f app.py && test -f dex_migrations.py && test -f dex_economics.py && test -f dex_legacy_economics.py && python -c "import dex_migrations, dex_economics, dex_legacy_economics"'

[[ "$(docker compose ps -q dex)" == "$LIVE_CONTAINER_ID" ]] \
  || die "live Compose container changed during image build"
[[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER_ID")" == "$LIVE_CONTAINER_IMAGE_ID" ]] \
  || die "live Compose container image changed during image build"

SERVICE_USER="$(docker inspect --format '{{.Config.User}}' "$LIVE_CONTAINER_ID")"
RUN_USER=()
if [[ -n "$SERVICE_USER" ]]; then
  RUN_USER=(--user "$SERVICE_USER")
fi

log "copying live storage without stopping production"
cp -a "$LIVE_STORAGE/." "$COPY_STORAGE/"

docker run --rm \
  "${RUN_USER[@]}" \
  -v "$LIVE_STORAGE:/live:ro" \
  -v "$COPY_STORAGE:/copy" \
  --entrypoint python \
  "$RESOLVED_IMAGE" \
  -c "import sqlite3
source = sqlite3.connect('file:/live/dex.db?mode=ro', uri=True)
target = sqlite3.connect('/copy/dex.snapshot.db')
source.backup(target)
target.close()
source.close()"

[[ -f "$COPY_STORAGE/dex.snapshot.db" ]] || die "SQLite online backup was not created"
mv "$COPY_STORAGE/dex.snapshot.db" "$COPY_STORAGE/dex.db"
for sqlite_sidecar in dex.db-wal dex.db-shm; do
  if [[ -e "$COPY_STORAGE/$sqlite_sidecar" ]]; then
    mv "$COPY_STORAGE/$sqlite_sidecar" "$AUDIT_DIR/copied-$sqlite_sidecar"
  fi
done
cp "$COPY_STORAGE/dex.db" "$AUDIT_DIR/dex.before.db"

log "checking copied database auto-purge state"
docker run --rm \
  "${RUN_USER[@]}" \
  -v "$COPY_STORAGE:/data:ro" \
  --entrypoint python \
  "$RESOLVED_IMAGE" \
  -c "import datetime, sqlite3, sys
db = sqlite3.connect('file:/data/dex.db?mode=ro', uri=True)
setting = db.execute(\"SELECT value FROM settings WHERE key='recycle_auto_purge'\").fetchone()
now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
eligible = db.execute(\"\"\"SELECT COUNT(*) FROM cards c
LEFT JOIN sale_items si ON si.card_id = c.id
WHERE c.recycled_at IS NOT NULL AND c.purge_after <= ? AND si.id IS NULL\"\"\", (now,)).fetchone()[0]
enabled = bool(setting and setting[0] == '1')
print({'auto_purge_enabled': enabled, 'eligible_cards': eligible})
sys.exit(2 if enabled and eligible else 0)" \
  | tee "$AUDIT_DIR/auto-purge-check.txt"

docker run --rm \
  "${RUN_USER[@]}" \
  -v "$COPY_STORAGE:/data:ro" \
  --entrypoint python \
  "$RESOLVED_IMAGE" \
  -c "import json, sqlite3
db = sqlite3.connect('file:/data/dex.db?mode=ro', uri=True)
result = {
  'batches': db.execute('SELECT COUNT(*) FROM batches').fetchone()[0],
  'active_batches': db.execute('SELECT COUNT(*) FROM batches WHERE recycled_at IS NULL').fetchone()[0],
  'cards': db.execute('SELECT COUNT(*) FROM cards').fetchone()[0],
  'active_cards': db.execute('SELECT COUNT(*) FROM cards WHERE recycled_at IS NULL').fetchone()[0],
  'recycled_cards': db.execute('SELECT COUNT(*) FROM cards WHERE recycled_at IS NOT NULL').fetchone()[0],
  'sale_orders': db.execute('SELECT COUNT(*) FROM sale_orders').fetchone()[0],
  'sale_items': db.execute('SELECT COUNT(*) FROM sale_items').fetchone()[0]
}
print(json.dumps(result, indent=2, sort_keys=True))" \
  | tee "$AUDIT_DIR/counts.before.json"

log "launching isolated temporary container on 127.0.0.1:$TEMP_PORT"
docker run -d \
  --name "$TEMP_NAME" \
  "${RUN_USER[@]}" \
  -p "127.0.0.1:$TEMP_PORT:8080" \
  -e DEX_DATA_DIR=/data \
  -e DEX_INBOUND_DIR=/tmp/dex-inbound \
  -e DEX_SOURCE_DB_DIR=/tmp/dex-source \
  -e DEX_WATCH_INBOUND=0 \
  -e DEX_SEED_DEMO=0 \
  -v "$COPY_STORAGE:/data" \
  --tmpfs /tmp \
  "$RESOLVED_IMAGE" >/dev/null
TEMP_STARTED=1

TEMP_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$TEMP_NAME")"
[[ "$TEMP_IMAGE_ID" == "$BUILT_IMAGE_ID" ]] \
  || die "temporary container did not use the freshly built Compose image"

TEMP_MOUNTS="$(docker inspect --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}' "$TEMP_NAME")"
printf '%s\n' "$TEMP_MOUNTS" | tee "$AUDIT_DIR/temporary-mounts.txt"
printf '%s\n' "$TEMP_MOUNTS" | grep -Fxq "$COPY_STORAGE -> /data" \
  || die "temporary container is not mounted to copied storage"
if printf '%s\n' "$TEMP_MOUNTS" | grep -Fq "$LIVE_STORAGE ->"; then
  die "temporary container unexpectedly mounts live storage"
fi

BASE_URL="http://127.0.0.1:$TEMP_PORT"
health_ready=0
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if [[ "$(curl -sS -o "$AUDIT_DIR/health.json" -w '%{http_code}' "$BASE_URL/api/health" || true)" == "200" ]]; then
    health_ready=1
    break
  fi
  sleep 1
done
[[ "$health_ready" -eq 1 ]] || {
  docker logs "$TEMP_NAME" >"$AUDIT_DIR/container.log" 2>&1 || true
  die "temporary application did not return HTTP 200 from /api/health"
}

fetch_200() {
  local endpoint=$1
  local destination=$2
  local status
  status="$(curl -sS -o "$destination" -w '%{http_code}' "$BASE_URL$endpoint" || true)"
  [[ "$status" == "200" ]] || die "$endpoint returned HTTP $status"
}

fetch_200 /api/dashboard "$AUDIT_DIR/dashboard.json"
fetch_200 /api/inventory "$AUDIT_DIR/inventory.json"
fetch_200 /api/batches "$AUDIT_DIR/batches.json"
fetch_200 /api/recycle "$AUDIT_DIR/recycle.json"

docker run --rm \
  "${RUN_USER[@]}" \
  -v "$AUDIT_DIR:/audit:ro" \
  --entrypoint python \
  "$RESOLVED_IMAGE" \
  -c "import json
load = lambda name: json.load(open('/audit/' + name, encoding='utf-8'))
health = load('health.json')
counts = load('counts.before.json')
dashboard = load('dashboard.json')
inventory = load('inventory.json')
batches = load('batches.json')
recycle = load('recycle.json')
assert health.get('status') == 'ok', health
assert health.get('version') == 'v2.1-test', health
assert isinstance(inventory.get('groups'), list), inventory
assert isinstance(batches.get('batches'), list), batches
assert isinstance(recycle.get('cards'), list), recycle
assert dashboard.get('total_cards') == counts['active_cards'], (dashboard, counts)
assert dashboard.get('recycled_count') == counts['recycled_cards'], (dashboard, counts)
assert len(batches['batches']) == counts['active_batches'], (batches, counts)
assert len(recycle['cards']) == counts['recycled_cards'], (recycle, counts)
inventory_copies = sum(len(group.get('copies', [])) for group in inventory['groups'])
assert inventory_copies == counts['active_cards'], (inventory_copies, counts)
print('API counts and v2.1-test runtime identity verified')"

BATCH_ID="$(docker run --rm \
  "${RUN_USER[@]}" \
  -v "$AUDIT_DIR:/audit:ro" \
  --entrypoint python \
  "$RESOLVED_IMAGE" \
  -c "import json
batches = json.load(open('/audit/batches.json', encoding='utf-8'))['batches']
if not batches:
    raise SystemExit('No active batch exists for the economics gate')
preferred = next((item for item in batches if float(item.get('total_cost') or 0) > 0), batches[0])
print(preferred['id'])")"

fetch_200 "/api/batches/$BATCH_ID/economics/estimate" "$AUDIT_DIR/economics-$BATCH_ID.json"
docker run --rm \
  "${RUN_USER[@]}" \
  -v "$AUDIT_DIR:/audit:ro" \
  --entrypoint python \
  "$RESOLVED_IMAGE" \
  -c "import json
estimate = json.load(open('/audit/economics-$BATCH_ID.json', encoding='utf-8'))
assert estimate.get('state') == 'ESTIMATED', estimate
assert estimate.get('calculation_version'), estimate
assert 'Estimate only' in estimate.get('notice', ''), estimate
print('Estimated Economics endpoint verified for batch $BATCH_ID')"

docker logs "$TEMP_NAME" >"$AUDIT_DIR/container.log" 2>&1
docker stop "$TEMP_NAME" >/dev/null
docker rm "$TEMP_NAME" >/dev/null
TEMP_STARTED=0
[[ -z "$(docker ps -aq --filter "name=^${TEMP_NAME}$")" ]] \
  || die "temporary container still exists after cleanup"

cp "$COPY_STORAGE/dex.db" "$AUDIT_DIR/dex.after.db"

log "comparing copied database before and after startup"
docker run --rm -i \
  "${RUN_USER[@]}" \
  -v "$AUDIT_DIR:/audit:ro" \
  --entrypoint python \
  "$RESOLVED_IMAGE" <<'PY' | tee "$AUDIT_DIR/database-comparison.txt"
import hashlib
import json
import sqlite3
import sys

def snapshot(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    schema = {
        (row[0], row[1]): row[2]
        for row in db.execute(
            """SELECT type, name, sql FROM sqlite_master
               WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"""
        )
    }
    tables = [
        row[0]
        for row in db.execute(
            """SELECT name FROM sqlite_master
               WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"""
        )
    ]
    data = {}
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        rows = sorted(repr(tuple(row)) for row in db.execute(f"SELECT * FROM {quoted}"))
        data[table] = {
            "rows": len(rows),
            "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest(),
        }
    db.close()
    return schema, data

before_schema, before_data = snapshot('/audit/dex.before.db')
after_schema, after_data = snapshot('/audit/dex.after.db')

added = sorted(set(after_schema) - set(before_schema))
removed = sorted(set(before_schema) - set(after_schema))
changed_schema = sorted(
    key for key in set(before_schema) & set(after_schema)
    if before_schema[key] != after_schema[key]
)
changed_data = {
    table: {"before": before_data.get(table), "after": after_data.get(table)}
    for table in sorted(set(before_data) | set(after_data))
    if before_data.get(table) != after_data.get(table)
}

result = {
    "schema_added": added,
    "schema_removed": removed,
    "schema_changed": changed_schema,
    "data_changed": changed_data,
}
print(json.dumps(result, indent=2))

empty_digest = hashlib.sha256(b'').hexdigest()
expected = (
    added == [('table', 'schema_migrations')]
    and not removed
    and not changed_schema
    and changed_data == {
        'schema_migrations': {
            'before': None,
            'after': {'rows': 0, 'sha256': empty_digest},
        }
    }
)
if not expected:
    print('FAIL: logical database changes exceeded the empty migration ledger.', file=sys.stderr)
    sys.exit(1)
print('PASS: only the empty schema_migrations ledger was added.')
PY

[[ "$(docker compose ps -q dex)" == "$LIVE_CONTAINER_ID" ]] \
  || die "live Compose container identity changed"
[[ "$(docker inspect --format '{{.Image}}' "$LIVE_CONTAINER_ID")" == "$LIVE_CONTAINER_IMAGE_ID" ]] \
  || die "live Compose container image changed"
[[ "$(docker inspect --format '{{.State.Running}}' "$LIVE_CONTAINER_ID")" == "true" ]] \
  || die "live Compose container is no longer running"

GATE_PASSED=1
