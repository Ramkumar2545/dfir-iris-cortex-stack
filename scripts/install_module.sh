#!/usr/bin/env bash
# =============================================================
# Install IrisCortexModule v3 into running IRIS containers
# Run AFTER docker compose up -d and containers are healthy.
#
# FIX: Use /opt/venv/bin/pip — the IRIS image installs everything
#      into /opt/venv.  Using bare `pip` or `pip3` hits the system
#      Python and the module is never visible to the IRIS app.
# =============================================================
set -euo pipefail

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}  $*"; }
info() { echo -e "${BLUE}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

VENV_PIP="/opt/venv/bin/pip"
MODULE_URL="git+https://github.com/Ramkumar2545/dfir-iris-cortex-stack.git#subdirectory=iris_module"

install_into() {
    local container="$1"
    info "Installing IrisCortexModule v3 into ${container} (${VENV_PIP})..."
    docker exec "${container}" "${VENV_PIP}" install --upgrade --quiet "${MODULE_URL}"
    ok "Installed in ${container}"

    # Verify the entry point is now visible inside the venv
    info "Verifying entry point in ${container}..."
    if docker exec "${container}" /opt/venv/bin/python3 -c "
import importlib.metadata
eps = importlib.metadata.entry_points(group='iris_module')
names = [ep.name for ep in eps]
print('Entry points:', names)
assert 'IrisCortexModuleV3' in names, 'Entry point NOT found!'
"; then
        ok "Entry point IrisCortexModuleV3 confirmed in ${container}"
    else
        warn "Entry point check failed in ${container} — module may not load correctly"
    fi
}

install_into iriswebapp_app
install_into iriswebapp_worker

info "Restarting app and worker to pick up the new module..."
docker compose restart app worker
ok "Containers restarted"

info "Waiting 25s for worker to fully initialise..."
sleep 25

info "Worker tail log (last 15 lines):"
docker compose logs worker --tail=15 | grep -E 'ready|ERROR|celery|IrisCortex' || true

ok "Module installation complete!"
info "Next: IRIS UI → Advanced → Modules → Add 'IrisCortexModuleV3' → Enable → Configure"
info "Hooks registered: on_postload_ioc_create, on_postload_ioc_update"
