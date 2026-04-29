#!/usr/bin/env bash
# buildnpush2iris.sh — build the iris_cortex_module_v3 wheel and install
# it into the running DFIR-IRIS Docker containers.
#
# Usage:
#   ./buildnpush2iris.sh -a
set -euo pipefail

MODE="${1:-}"
MODULE_PKG="iris_module"        # subdirectory containing setup.py / pyproject.toml
APP_CONTAINER="iriswebapp_app"
WORKER_CONTAINER="iriswebapp_worker"
VENV_PIP="/opt/venv/bin/pip"    # IRIS venv pip — NOT bare pip
GIT_URL="git+https://github.com/Ramkumar2545/dfir-iris-cortex-stack.git#subdirectory=${MODULE_PKG}"

if [[ "$MODE" != "-a" ]]; then
  echo "Usage: ./buildnpush2iris.sh -a"
  exit 1
fi

echo "[+] Installing into ${APP_CONTAINER} ..."
docker exec "${APP_CONTAINER}" "${VENV_PIP}" install --upgrade "${GIT_URL}"

echo "[+] Installing into ${WORKER_CONTAINER} ..."
docker exec "${WORKER_CONTAINER}" "${VENV_PIP}" install --upgrade "${GIT_URL}"

echo ""
echo "[+] Done. Restarting containers ..."
docker compose restart app worker

echo ""
echo "[i] Verify entry point registration:"
echo "    docker exec ${APP_CONTAINER} python3 -c \""
echo "      import importlib.metadata"
echo "      eps = importlib.metadata.entry_points(group='iris_module')"
echo "      [print(ep.name, '->', ep.value) for ep in eps]"
echo "    \""
