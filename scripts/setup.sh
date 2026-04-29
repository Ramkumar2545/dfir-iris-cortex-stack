#!/usr/bin/env bash
# =============================================================
# DFIR-IRIS + Cortex 4.x — Setup Script
# Run once before first: docker compose up -d
# =============================================================
set -euo pipefail

BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()     { echo -e "${RED}[ERR]${NC}  $*" >&2; exit 1; }

info "=== DFIR-IRIS + Cortex 4.x Setup ==="

# ── 1. Kernel param for Elasticsearch ──────────────────────
info "Setting vm.max_map_count=262144 (Elasticsearch requirement)"
sudo sysctl -w vm.max_map_count=262144
grep -q 'vm.max_map_count' /etc/sysctl.conf \
  || echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf > /dev/null
ok "vm.max_map_count=262144 set persistently"

# ── 2. Cortex job directory ─────────────────────────────────
info "Creating /tmp/cortex-jobs"
mkdir -p /tmp/cortex-jobs
chmod 777 /tmp/cortex-jobs
ok "/tmp/cortex-jobs ready"

# ── 3. Cortex config/log dirs ──────────────────────────────
# /var/log/cortex must be writable by cortex uid 1001
# /etc/cortex must NOT be :ro — entrypoint chowns it on startup
info "Creating cortex directories with correct permissions"
mkdir -p cortex/config cortex/logs cortex/neurons
chmod -R 777 cortex/logs
chmod -R 755 cortex/config
chmod -R 755 cortex/neurons
ok "Cortex dirs ready: cortex/config cortex/logs cortex/neurons"

# ── 4. TLS certificates ─────────────────────────────────────
info "Generating self-signed TLS certificate (10 years)"
mkdir -p certificates/web_certificates certificates/rootCA certificates/ldap
touch certificates/ldap/.keep

if [ ! -f certificates/web_certificates/iris.crt ]; then
  openssl req -x509 -nodes -days 3650 -newkey rsa:4096 \
    -keyout certificates/web_certificates/iris.key \
    -out   certificates/web_certificates/iris.crt \
    -subj  "/C=IN/ST=TN/L=Chennai/O=DFIR/CN=iris.local" 2>/dev/null
  cp certificates/web_certificates/iris.crt certificates/rootCA/irisRootCACert.pem
  ok "TLS cert generated"
else
  ok "TLS cert already exists — skipping"
fi

# ── 4b. Fix TLS cert/key permissions ───────────────────────────
# FIX: openssl generates iris.key as 600 (root-only read).
# The nginx container runs as non-root — it cannot read a 600 key
# through the volume mount, causing:
#   "cannot load certificate key '/www/certs/iris.key': Permission denied"
# 644 makes the key world-readable (acceptable for a self-signed lab cert).
info "Setting TLS cert/key permissions to 644 (nginx readable)"
chmod 644 certificates/web_certificates/iris.key
chmod 644 certificates/web_certificates/iris.crt
chmod 644 certificates/rootCA/irisRootCACert.pem
ok "certificates/web_certificates/iris.key → 644"
ok "certificates/web_certificates/iris.crt → 644"

# ── 5. .env file setup ──────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  SALT=$(python3   -c "import secrets; print(secrets.token_hex(16))")
  DBPASS="IrisDB$(openssl rand -hex 8)"
  DBADMIN="IrisAdmin$(openssl rand -hex 8)"

  sed -i "s|CHANGE_ME_secret_key_min_32_chars|${SECRET}|g" .env
  sed -i "s|CHANGE_ME_password_salt|${SALT}|g" .env
  sed -i "s|CHANGE_ME_db_password|${DBPASS}|g" .env
  sed -i "s|CHANGE_ME_admin_password|${DBADMIN}|g" .env
  sed -i "s|^DB_PASS=.*|DB_PASS=${DBPASS}|"       .env

  ok ".env created with auto-generated secrets"
  warn "Review before production: nano .env"
else
  ok ".env already exists — skipping auto-generation"
fi

# ── 6. Final check ──────────────────────────────────────────
info "Verifying critical .env keys..."
for KEY in SECRET_KEY SECURITY_PASSWORD_SALT DB_PASS DB_HOST; do
  VAL=$(grep "^${KEY}=" .env | cut -d'=' -f2- || true)
  if [ -z "$VAL" ] || echo "$VAL" | grep -qi 'change_me'; then
    err "${KEY} is missing or still placeholder! Edit .env"
  fi
  ok "  ${KEY} = ${VAL:0:12}..."
done

info "=== Setup complete ==="
info "Next: docker compose up -d"
info "Then: docker compose ps  (wait ~90s for all containers healthy)"
