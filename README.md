# 🔍 DFIR-IRIS + Cortex 4.x — Complete Docker Stack

> **Single-machine deployment** of [DFIR-IRIS](https://github.com/dfir-iris/iris-web) + [Cortex 4.x](https://github.com/TheHive-Project/Cortex) with the **IrisCortexModule v3** — a native `requests`-based integration that works with Cortex 3.x **and** 4.x without `cortex4py`.

[![IRIS](https://img.shields.io/badge/DFIR--IRIS-v2.4.20-blue)](https://github.com/dfir-iris/iris-web)
[![Cortex](https://img.shields.io/badge/Cortex-4.0.0-orange)](https://github.com/TheHive-Project/Cortex)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 📋 Table of Contents

1. [Architecture](#architecture)
2. [Requirements](#requirements)
3. [Quick Start](#quick-start)
4. [Step-by-Step Deployment](#step-by-step-deployment)
 - [Step 1 — Clone & Configure](#step-1--clone--configure)
 - [Step 2 — Generate TLS Certificates](#step-2--generate-tls-certificates)
 - [Step 3 — Set Environment Variables](#step-3--set-environment-variables)
 - [Step 4 — Start the Stack](#step-4--start-the-stack)
 - [Step 5 — Verify Services](#step-5--verify-services)
 - [Step 6 — Set Up Cortex](#step-6--set-up-cortex)
 - [Step 7 — Install the IRIS Cortex Module](#step-7--install-the-iris-cortex-module)
 - [Step 8 — Configure Module in IRIS UI](#step-8--configure-module-in-iris-ui)
 - [Step 9 — Test End-to-End](#step-9--test-end-to-end)
5. [Known Issues & Fixes](#known-issues--fixes)
6. [Service Access](#service-access)
7. [RAM Allocation](#ram-allocation)
8. [Troubleshooting](#troubleshooting)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Single Machine (16 GB RAM) │
│ │
│ ┌──────────┐ ┌──────────────┐ ┌─────────┐ │
│ │ Nginx │──▶│ IRIS WebApp │──▶│ Worker │ │
│ │ :443 │ │ :8000 │ │ Celery │ │
│ └──────────┘ └──────┬───────┘ └────┬────┘ │
│ │ │ │
│ ┌──────▼───────┐ ┌────▼────────┐ │
│ │ PostgreSQL │ │ RabbitMQ │ │
│ │ (iris_db) │ │ :5672 │ │
│ └──────────────┘ └─────────────┘ │
│ │
│ ┌──────────────────────────────────┐ │
│ │ Cortex :9001 /cortex/api/... │ │
│ │ + Elasticsearch :9200 │ │
│ └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

IRIS Worker ──[HTTP]──▶ Cortex API ──[Docker]──▶ Analyzer containers
 (IrisCortexModule v3) (VirusTotal, etc.)
```

---

## Requirements

| Item | Minimum |
|---|---|
| RAM | 16 GB |
| CPU | 4 cores |
| Disk | 40 GB free |
| OS | Ubuntu 22.04 / 24.04 LTS |
| Docker | 24.x+ |
| Docker Compose | v2.x (`docker compose`) |
| Internet | Required for analyzer pulls |

```bash
# Verify Docker versions
docker --version
docker compose version
```

---

## Quick Start

```bash
git clone https://github.com/Ramkumar2545/dfir-iris-cortex-stack.git
cd dfir-iris-cortex-stack
bash scripts/setup.sh
```

Then open:
- **IRIS** → `https://<YOUR_IP>` (admin / irisadmin)
- **Cortex** → `http://<YOUR_IP>:9001`

---

## Step-by-Step Deployment

### Step 1 — Clone & Configure

```bash
git clone https://github.com/Ramkumar2545/dfir-iris-cortex-stack.git
cd dfir-iris-cortex-stack
```

### Step 2 — Generate TLS Certificates

IRIS requires TLS. Generate a self-signed cert:

```bash
mkdir -p certificates/web_certificates certificates/rootCA certificates/ldap

# Self-signed cert (valid 10 years)
openssl req -x509 -nodes -days 3650 -newkey rsa:4096 \
 -keyout certificates/web_certificates/iris.key \
 -out certificates/web_certificates/iris.crt \
 -subj "/C=IN/ST=TN/L=Chennai/O=DFIR/CN=iris.local"

# Copy root CA (IRIS requires this file to exist)
cp certificates/web_certificates/iris.crt certificates/rootCA/irisRootCACert.pem

# Create empty ldap cert dir placeholder
touch certificates/ldap/.keep
```

### Step 3 — Set Environment Variables

> ⚠️ **CRITICAL**: Variable names must match EXACTLY. Wrong names = `SECRET_KEY = None` = worker crash.
> See [Known Issues #1](#known-issues--fixes) for full explanation.

```bash
# Copy the example
cp .env.example .env

# Generate REAL secrets (never use CHANGE_ME in production)
SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
SALT=$(python3 -c "import secrets; print(secrets.token_hex(16))")

# Inject into .env
sed -i "s|CHANGE_ME_secret_key_min_32_chars|${SECRET}|g" .env
sed -i "s|CHANGE_ME_password_salt|${SALT}|g" .env
sed -i "s|CHANGE_ME_db_password|IrisDB$(openssl rand -hex 8)|g" .env
sed -i "s|CHANGE_ME_admin_password|IrisAdmin$(openssl rand -hex 8)|g" .env

# Sync DB_PASS with POSTGRES_PASSWORD
DB_PASS=$(grep '^POSTGRES_PASSWORD=' .env | cut -d'=' -f2-)
sed -i "s|^DB_PASS=.*|DB_PASS=${DB_PASS}|" .env

# Verify — must show all 4 lines with real values
grep -E '^SECRET_KEY=|^SECURITY_PASSWORD_SALT=|^DB_PASS=|^DB_HOST=' .env
```

**Expected output:**
```
SECRET_KEY=<64-char hex>
SECURITY_PASSWORD_SALT=<32-char hex>
DB_PASS=IrisDB<random>
DB_HOST=db
```

### Step 4 — Start the Stack

```bash
# Set required kernel parameter for Elasticsearch
sudo sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf

# Start all services
docker compose up -d

# Watch startup (takes ~90s first boot)
docker compose logs -f --tail=20
```

### Step 5 — Verify Services

```bash
# All containers must show healthy/running
docker compose ps

# Quick health check
echo "=== IRIS ==="
curl -sk https://localhost/api/ping | python3 -m json.tool

echo "=== Cortex ==="
curl -s http://localhost:9001/cortex/api/status | python3 -m json.tool

echo "=== Elasticsearch ==="
curl -s http://localhost:9200/_cat/health

# Worker MUST show 'celery@xxxx ready.' with NO errors
docker compose logs worker --tail=20 | grep -E 'ready|ERROR|Secret'
```

### Step 6 — Set Up Cortex

1. Open `http://<YOUR_IP>:9001` in browser
2. First run → **Update Database** → wait for migration
3. Create **admin user** → login
4. Go to **Organization** → **Create Organization** (e.g. `IRIS`)
5. Switch to org → **Users** → **Create User** → Role: `orgAdmin`
6. Click user → **API Keys** → **Create** → **Copy the key** ← needed for Step 8
7. Go to **Analyzers** → Enable the analyzers you want (e.g. `VirusTotal_GetReport_3_1`)

> ⚠️ **Cortex 4.x API path changed** — all API calls are now at `/cortex/api/...` not `/api/...`
> The IrisCortexModule v3 auto-detects this. See [Known Issues #3](#known-issues--fixes).

### Step 7 — Install the IRIS Cortex Module

The module must be installed in **both** the `app` and `worker` containers:

```bash
# Install in app container (handles hook registration)
docker exec iriswebapp_app pip install --upgrade \
 'git+https://github.com/Ramkumar2545/dfir-iris-cortex-stack.git#subdirectory=iris_module'

# Install in worker container (handles job execution)
docker exec iriswebapp_worker pip install --upgrade \
 'git+https://github.com/Ramkumar2545/dfir-iris-cortex-stack.git#subdirectory=iris_module'

# Restart both to pick up the new module
docker compose restart app worker

# Verify installation
docker exec iriswebapp_app pip show iris-cortex-module-v3
docker exec iriswebapp_worker pip show iris-cortex-module-v3
```

### Step 8 — Configure Module in IRIS UI

1. Open `https://<YOUR_IP>` → login as `administrator` / `irisadmin`
2. Go to **Advanced** → **Modules**
3. Click **➕ Add Module** → enter class name: `IrisCortexModuleV3`
4. Click **Enable** on the module
5. Click **⚙️ Configure** and set:

| Parameter | Value | Notes |
|---|---|---|
| `cortex_url` | `http://<YOUR_IP>:9001` | No `/cortex` suffix — module auto-detects |
| `cortex_api_key` | *(from Step 6)* | orgAdmin API key |
| `cortex_analyzers` | `VirusTotal_GetReport_3_1` | One per line or comma-separated |
| `auto_select_analyzers` | `false` | Set `true` to auto-pick by IOC type |
| `report_as_attribute` | `true` | Saves report to IOC custom attributes |
| `job_timeout_seconds` | `300` | Max wait per analyzer job |
| `verify_ssl` | `false` | Set `true` if Cortex has valid TLS |

6. Click **Save** → green ✅ toast = success

### Step 9 — Test End-to-End

```bash
# Watch worker in real time
docker compose logs worker -f 2>&1 | grep -iE 'cortex|ioc|hook|saved|error'
```

In IRIS UI:
1. Open **Cases** → create or open a case
2. Go to **IOCs** tab → add an IOC (e.g. `8.8.8.8`, type `ip`)
3. Right-click the IOC → **Run Cortex Analyzers v3**
4. Watch the worker logs:

```
[IrisCortex v3] Hook fired: on_manual_trigger_ioc
[IrisCortex v3] Cortex client initialised → http://192.168.31.144:9001/cortex
[IrisCortex v3] IOC='8.8.8.8' | IRIS=ip | Cortex=ip
[IrisCortex v3] ▶ VirusTotal_GetReport_3_1 ← '8.8.8.8' (ip)
[IrisCortex v3] Job submitted: <job_id>
[IrisCortex v3] Job <job_id> finished: Success
[IrisCortex v3] ✔ Saved: CORTEX v3: VirusTotal_GetReport_3_1
```

5. Refresh IOC → **Custom Attributes** → report appears ✅

---

## Known Issues & Fixes

All issues below were encountered and resolved during real deployment.

---

### ❌ Issue 1: `TypeError: encoding without a string argument`

**Symptom:**
```
iriswebapp_worker | TypeError: encoding without a string argument
 File "/iriswebapp/app/util.py", line 850, in hmac_verify
 key = bytes(app.config.get("SECRET_KEY"), "utf-8")
```

**Root Cause:** `app.config.get("SECRET_KEY")` returns `None` because the `.env` file used the wrong variable name `IRIS_SECRET_KEY` instead of `SECRET_KEY`. IRIS reads `SECRET_KEY` directly — no prefix.

**Fix:**
```bash
# Check what name you have
grep -E 'SECRET' .env

# If it shows IRIS_SECRET_KEY — rename it:
VAL=$(grep '^IRIS_SECRET_KEY=' .env | cut -d'=' -f2-)
sed -i '/^IRIS_SECRET_KEY=/d' .env
echo "SECRET_KEY=${VAL}" >> .env

# Same for salt
VAL2=$(grep '^IRIS_SECURITY_PASSWORD_SALT=' .env | cut -d'=' -f2-)
sed -i '/^IRIS_SECURITY_PASSWORD_SALT=/d' .env
echo "SECURITY_PASSWORD_SALT=${VAL2}" >> .env

# MUST do full down+up — restart does NOT reload .env
docker compose down && docker compose up -d
```

> ⚠️ `docker compose restart` does **NOT** reload `.env`. Always use `down` + `up`.

---

### ❌ Issue 2: `RuntimeError: Working outside of application context`

**Symptom:**
```
RuntimeError: Working outside of application context.
This typically means that you attempted to use functionality that needed
the current application.
```

**Root Cause:** This is a **secondary error** caused by Issue 1. The worker's `hmac_verify()` crashes before establishing the Flask app context. Fix Issue 1 and this disappears automatically.

---

### ❌ Issue 3: `cortex4py` incompatible with Cortex 4.x

**Symptom:** Module connects but all analyzer calls fail with 404 or connection error.

**Root Cause:** `cortex4py 2.x` was built for Cortex 3.x where the API is at `/api/...`. Cortex 4.x moved the base path to `/cortex/api/...`. `cortex4py` has no sub-path configuration option.

**Fix:** IrisCortexModule v3 replaces `cortex4py` entirely with native `requests` and auto-detects the correct base path:
```python
# Probes /cortex/api/status first (Cortex 4.x)
# Falls back to /api/status (Cortex 3.x)
# No manual configuration needed
```

---

### ❌ Issue 4: `Unable to update hooks` in IRIS UI

**Symptom:** Clicking Save in module config shows red toast: `Unable to update hooks`

**Root Cause:** Module is installed only in the `worker` container but IRIS registers hooks from the `app` container.

**Fix:**
```bash
# Install in BOTH containers
docker exec iriswebapp_app pip install --upgrade \
 'git+https://github.com/Ramkumar2545/dfir-iris-cortex-stack.git#subdirectory=iris_module'
docker exec iriswebapp_worker pip install --upgrade \
 'git+https://github.com/Ramkumar2545/dfir-iris-cortex-stack.git#subdirectory=iris_module'
docker compose restart app worker
```

---

### ❌ Issue 5: Elasticsearch `vm.max_map_count` too low

**Symptom:** `cortex_es` container exits immediately with `max virtual memory areas vm.max_map_count [65530] is too low`

**Fix:**
```bash
sudo sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf
docker compose restart elasticsearch
```

---

### ❌ Issue 6: Cortex `AccessDeniedException` for job directory

**Symptom:** Analyzer jobs fail with `java.nio.file.AccessDeniedException: /tmp/cortex-jobs/cortex-job-*`

**Fix:** The `docker-compose.yml` in this repo already sets `user: "0:0"` on the Cortex container and mounts `/tmp/cortex-jobs` from host with open permissions. Ensure:
```bash
mkdir -p /tmp/cortex-jobs
chmod 777 /tmp/cortex-jobs
```

---

## Service Access

| Service | URL | Default Credentials |
|---|---|---|
| IRIS UI | `https://<YOUR_IP>` | `administrator` / `irisadmin` |
| Cortex UI | `http://<YOUR_IP>:9001` | *(set on first run)* |
| RabbitMQ Mgmt | `http://<YOUR_IP>:15672` | `guest` / `guest` |
| Elasticsearch | `http://<YOUR_IP>:9200` | *(no auth — internal only)* |

---

## RAM Allocation

| Service | Memory Limit | Notes |
|---|---|---|
| `elasticsearch` | 3 GB | ES heap: `-Xms1g -Xmx2g` |
| `iris app` | 2 GB | WebApp + uWSGI |
| `cortex` | 2 GB | JVM heap: `-Xms1g -Xmx1g` |
| `iris worker` | 1 GB | Celery |
| `db` | 1 GB | PostgreSQL |
| `rabbitmq` | 512 MB | Message broker |
| `nginx` | 256 MB | Reverse proxy |
| **OS + headroom** | ~6 GB | Safe on 16 GB host |

---

## Troubleshooting

### Worker not starting clean
```bash
# Check worker env — must show SECRET_KEY not IRIS_SECRET_KEY
docker exec iriswebapp_worker env | grep -E 'SECRET_KEY|SECURITY_PASSWORD'

# Check full worker logs
docker compose logs worker --tail=50
```

### Module not appearing in IRIS UI
```bash
# Verify module installed in app container
docker exec iriswebapp_app pip show iris-cortex-module-v3

# Check app logs for import errors
docker compose logs app --tail=30 | grep -iE 'error|module|import|cortex'
```

### Cortex analyzer 404
```bash
# List enabled analyzers in your org
curl -s -H "Authorization: Bearer YOUR_API_KEY" \
 http://localhost:9001/cortex/api/analyzer \
 | python3 -c "import sys,json; [print(a['name']) for a in json.load(sys.stdin)]"
```

### Full stack reset (nuclear option)
```bash
docker compose down -v # WARNING: deletes all data
docker compose up -d
```

---

## License

MIT — see [LICENSE](LICENSE)

---

> Built and battle-tested by [@Ramkumar2545](https://github.com/Ramkumar2545)
