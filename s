#!/bin/sh
set -e

log() { echo "[boot $(date -u +%H:%M:%S)] $*"; }

on_exit() {
  rc=$?
  if [ "$rc" -ne 0 ]; then
    log "FATAL: entrypoint exited with code $rc"
  fi
  exit "$rc"
}
trap on_exit EXIT

log "===== prompts.chat container starting ====="
log "node=$(node -v)  user=$(id -un 2>/dev/null || echo '?')  pwd=$(pwd)"

# ---------------------------------------------------------------------------
# Stage 0: what did the platform actually hand us?
# ---------------------------------------------------------------------------
log "--- environment ---"
log "PORT=${PORT:-<UNSET>}"
log "HOSTNAME=${HOSTNAME:-<UNSET>}"
log "NODE_ENV=${NODE_ENV:-<UNSET>}"
log "NEXTAUTH_URL=${NEXTAUTH_URL:-<UNSET>}"
log "AUTH_TRUST_HOST=${AUTH_TRUST_HOST:-<UNSET>}"
if [ -n "$AUTH_SECRET" ]; then log "AUTH_SECRET=<set>"; else log "AUTH_SECRET=<UNSET>"; fi
if [ -n "$DATABASE_URL" ]; then log "DATABASE_URL=<set>"; else log "DATABASE_URL=<UNSET>"; fi
if [ -n "$DIRECT_URL" ]; then log "DIRECT_URL=<set>"; else log "DIRECT_URL=<UNSET>"; fi
log "PCHAT_NAME=${PCHAT_NAME:-<UNSET>}"

if [ -f /app/.env ]; then
  log "WARNING: /app/.env exists inside the image and Next will load it. Check .dockerignore."
fi

if [ -z "$AUTH_SECRET" ]; then
  AUTH_SECRET=$(openssl rand -base64 32)
  export AUTH_SECRET
  log "WARNING: AUTH_SECRET was not set, generated a random one."
  log "WARNING: sessions will be invalidated on every restart until you pin it."
fi

if [ -z "$DATABASE_URL" ]; then
  log "FATAL: DATABASE_URL is not set. Nothing to connect to."
  exit 10
fi

# ---------------------------------------------------------------------------
# Stage 1: DNS + TCP, with the real error surfaced
# ---------------------------------------------------------------------------
log "--- stage 1: database reachability ---"

probe_db() {
  node -e '
    const dns = require("dns"), net = require("net");
    let u;
    try { u = new URL(process.env.DATABASE_URL); }
    catch (e) { console.log("  DATABASE_URL is unparseable as a URL"); process.exit(2); }
    const host = u.hostname;
    const port = Number(u.port || 5432);
    const dbname = (u.pathname || "").replace(/^\//, "") || "<none>";
    console.log("  host=" + host + " port=" + port + " db=" + dbname + " user=" + (u.username || "<none>"));
    console.log("  query=" + (u.search || "<none>"));
    dns.lookup(host, (err, addr) => {
      if (err) { console.log("  DNS FAILED: " + host + " -> " + err.code); process.exit(3); }
      console.log("  DNS ok: " + host + " -> " + addr);
      const s = net.createConnection({ host: addr, port: port });
      s.setTimeout(5000);
      s.on("connect", () => { console.log("  TCP ok: " + addr + ":" + port); s.destroy(); process.exit(0); });
      s.on("timeout", () => { console.log("  TCP TIMEOUT: " + addr + ":" + port + " (firewall?)"); s.destroy(); process.exit(4); });
      s.on("error", (e) => { console.log("  TCP FAILED: " + addr + ":" + port + " -> " + e.code); process.exit(5); });
    });
  '
}

MAX_RETRIES=30
RETRY_COUNT=0
until probe_db; do
  RETRY_COUNT=$((RETRY_COUNT + 1))
  if [ "$RETRY_COUNT" -ge "$MAX_RETRIES" ]; then
    log "FATAL: database unreachable after ${MAX_RETRIES} attempts. See the codes above."
    exit 11
  fi
  log "retry ${RETRY_COUNT}/${MAX_RETRIES} in 2s..."
  sleep 2
done
log "stage 1 passed (TCP only, this does NOT prove credentials work)"

# ---------------------------------------------------------------------------
# Stage 2: real authenticated connection
# ---------------------------------------------------------------------------
log "--- stage 2: authenticating (read-only) ---"
npx prisma migrate status 2>&1 || log "note: nonzero status above just means pending migrations"

# ---------------------------------------------------------------------------
# Stage 3: migrations
# ---------------------------------------------------------------------------
log "--- stage 3: migrations ---"
if npx prisma migrate deploy 2>&1; then
  log "stage 3 passed: migrations applied"
else
  log "FATAL: migrate deploy failed. Bad credentials, missing database, or a broken migration."
  exit 12
fi

# ---------------------------------------------------------------------------
# Stage 4: start Next, with a watcher that proves the port got bound
# ---------------------------------------------------------------------------
log "--- stage 4: starting next.js on port ${PORT:-3000} ---"

(
  i=0
  while [ "$i" -lt 45 ]; do
    i=$((i + 1))
    sleep 2
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 \
      "http://127.0.0.1:${PORT:-3000}/api/health" 2>/dev/null || echo "000")
    if [ "$code" != "000" ]; then
      log "LISTENING: /api/health returned HTTP $code after ~$((i * 2))s"
      if [ "$code" = "503" ]; then
        log "  (503 means Next is up but its db query failed)"
      fi
      root=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
        "http://127.0.0.1:${PORT:-3000}/" 2>/dev/null || echo "000")
      log "LISTENING: / returned HTTP $root (this is what App Service pings)"
      exit 0
    fi
  done
  log "WARNING: nothing answered on 127.0.0.1:${PORT:-3000} after 90s"
  log "WARNING: next.js either crashed or bound a different address"
) &

exec node server.js
