#!/usr/bin/env bash
# =============================================================
# Install IrisCortexModule v3 into running IRIS containers
# Run AFTER docker compose up -d and containers are healthy
# =============================================================
set -euo pipefail

GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}  $*"; }
info() { echo -e "${BLUE}[INFO]${NC} $*"; }

MODULE_URL="git+https://github.com/Ramkumar2545/dfir-iris-cortex-stack.git#subdirectory=iris_module"

info "Installing IrisCortexModule v3 into iriswebapp_app..."
docker exec iriswebapp_app pip install --upgrade --quiet "${MODULE_URL}"
ok "Installed in app container"

info "Installing IrisCortexModule v3 into iriswebapp_worker..."
docker exec iriswebapp_worker pip install --upgrade --quiet "${MODULE_URL}"
ok "Installed in worker container"

info "Restarting app and worker..."
docker compose restart app worker
ok "Containers restarted"

info "Waiting 20s for worker to init..."
sleep 20

info "Worker status:"
docker compose logs worker --tail=10 | grep -E 'ready|ERROR|celery' || true

ok "Module installation complete!"
info "Next: IRIS UI → Advanced → Modules → Add 'IrisCortexModuleV3' → Enable → Configure"
