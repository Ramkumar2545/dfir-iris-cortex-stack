#!/usr/bin/env bash
# =============================================================
# DFIR-IRIS + Cortex 4.x — Setup Script
# Run once before first docker compose up
# =============================================================
set -euo pipefail

BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}  $*"; }
error() { echo -e "${RED}[ERR]${NC}  $*" >&2; exit 1; }

info "=== DFIR-IRIS + Cortex Setup ==="

# ── Kernel param for Elasticsearch ──────────────────────────
info "Setting vm.max_map_count=262144 (required by Elasticsearch)"
sudo sysctl -w vm.max_map_count=262144
grep -q 'vm.max_map_count' /etc/sysctl.conf \
  || echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf
ok "Kernel param set"

# ── Cortex job directory ─────────────────────────────────────
info "Creating /tmp/cortex-jobs with open permissions"
mkdir -p /tmp/cortex-jobs
chmod 777 /tmp/cortex-jobs
ok "/tmp/cortex-jobs ready"

# ── TLS certificates ─────────────────────────────────────────
info "Generating self-signed TLS certificates"
mkdir -p certificates/web_certificates certificates/rootCA certificates/ldap
torch certificates/ldap/.keep 2>/dev/null || touch certificates/ldap/.keep

if [ ! -f certificates/web_certificates/iris.crt ]; then
  openssl req -x509 -nodes -days 3650 -newkey rsa:4096 \
    -keyout certificates/web_certificates/iris.key \
    -out  certificates/web_certificates/iris.crt \
    -subj "/C=IN/ST=TN/L=Chennai/O=DFIR/CN=iris.local" 2>/dev/null
  cp certificates/web_certificates/iris.crt certificates/rootCA/irisRootCACert.pem
  ok "TLS cert generated"
else
  ok "TLS cert already exists — skipping"
fi

# ── .env setup ───────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  SALT=$(python3 -c "import secrets; print(secrets.token_hex(16))")
  DBPASS="IrisDB$(openssl rand -hex 8)"
  DBADMIN="IrisAdmin$(openssl rand -hex 8)"

  sed -i "s|CHANGE_ME_secret_key_min_32_chars|${SECRET}|g" .env
  sed -i "s|CHANGE_ME_password_salt|${SALT}|g" .env
  sed -i "s|CHANGE_ME_db_password|${DBPASS}|g" .env
  sed -i "s|CHANGE_ME_admin_password|${DBADMIN}|g" .env

  # Keep DB_PASS in sync with POSTGRES_PASSWORD
  sed -i "s|^DB_PASS=.*|DB_PASS=${DBPASS}|" .env

  ok ".env created with auto-generated secrets"
  info "Review your .env: nano .env"
else
  ok ".env already exists — skipping auto-generation"
fi

# ── Cortex log dir ───────────────────────────────────────────
mkdir -p cortex/logs cortex/neurons
ok "Cortex directories ready"

info "=== Setup complete! ==="
info "Next step: docker compose up -d"
info "Then wait 90s and run: docker compose ps"
