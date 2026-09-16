#!/bin/bash
# End-to-end checks that the stack is actually public, read-only, and healthy.
# Run via `make verify`. Requires the stack to be up (`make up`).
set -uo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && . ./.env

fail=0
ok()   { echo "  ok   $1"; }
bad()  { echo "  FAIL $1"; fail=1; }

echo "== grafana health =="
if curl -sf http://localhost:3000/api/health | grep -q '"database": *"ok"'; then ok "database ok"; else bad "grafana /api/health"; fi

echo "== anonymous access =="
code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/api/search)
[ "$code" = "200" ] && ok "anonymous /api/search ($code)" || bad "anonymous /api/search ($code)"

code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  http://localhost:3000/api/dashboards/db -d '{}')
[ "$code" = "401" ] || [ "$code" = "403" ] && ok "anonymous write blocked ($code)" || bad "anonymous write blocked ($code)"

for uid in world-overview reserves markets city-weather earth-space fuel-prices collector-health \
           nl-economy nl-cost-of-living nl-housing-energy nl-weather nl-tourism nl-aircraft nl-trains; do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/api/dashboards/uid/$uid)
  [ "$code" = "200" ] && ok "dashboard $uid ($code)" || bad "dashboard $uid ($code)"
done

echo "== read-only database role =="
ro_out=$(docker compose exec -T postgres psql -U "${POSTGRES_RO_USER:-grafana_ro}" -d "${POSTGRES_DB:-mymon}" \
     -c "insert into city values('x','xx',0,0,'UTC')" 2>&1) || true
if echo "$ro_out" | grep -q "read-only transaction"; then
  ok "grafana_ro cannot write"
else
  bad "grafana_ro write was not rejected"
fi

echo "== prometheus scrape targets =="
targets=$(docker compose exec -T prometheus wget -qO- 'http://localhost:9090/api/v1/targets' 2>/dev/null)
for job in mymon-collector postgres grafana; do
  echo "$targets" | grep -q "\"job\":\"$job\".*\"health\":\"up\"" \
    && ok "prometheus target $job up" \
    || bad "prometheus target $job not up"
done

echo "== external reachability =="
if [ -n "${GRAFANA_ROOT_URL:-}" ]; then
  host=$(echo "$GRAFANA_ROOT_URL" | sed -E 's#^https?://##; s#:.*##')
  for flag in -4 -6; do
    if curl -s $flag --max-time 5 "http://$host:3000/api/health" >/dev/null 2>&1; then
      ok "reachable $flag over $host"
    else
      echo "  skip $flag over $host (not reachable from here, may be normal)"
    fi
  done
fi

if [ "$fail" -eq 0 ]; then echo; echo "All checks passed."; else echo; echo "Some checks FAILED."; fi
exit $fail
