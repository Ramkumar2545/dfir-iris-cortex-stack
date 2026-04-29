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
┌───────────────────────────────────────────────────────┐
│ Single Machine (16 GB RAM) │
│ │
│ ┌──────────┐ ┌──────────────┐ ┌─────────┐ │
│ │ Nginx │──▶│ IRIS WebApp │──▶│ Worker │ │
│ │ :443 │ │ :8000 │ │ Celery │ │
│ └──────────┘ └──────┬───────┘ └────┬────┘ │
│ │ │ │
│ ┌──────▼───────┐ ┌────▼──────────┐ │
│ │ PostgreSQL │ │ RabbitMQ │ │
│ │ (iris_db) │ │ :5672 │ │
│ └──────────────┘ └───────────────┘ │
│ │
│ ┌──────────────────────────────────┐ │
│ │ Cortex :9001 /cortex/api/... │ │
│ │ + Elasticsearch :9200 │ │
│ └──────────────────────────────────┘ │
└───────────────────────────────────────────────────────┘

IRIS Worker ──[HTTP]──▶ Cortex API ──[Docker]──▶ Analyzers
 (IrisCortexModule v3)
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

```bash
docker --version && docker compose version
```

---

## Quick Start

```bash
git clone https://github.com/Ramkumar2545/dfir-iris-cortex-stack.git
cd dfir-iris-cortex-stack
bash scripts/setup.sh
docker compose up -d
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

IRIS requires TLS. `bash scripts/setup.sh` does this automatically, or manually:

```bash
mkdir -p certificates/web_certificates certificates/rootCA certificates/ldap
touch certificates/ldap/.keep

openssl req -x509 -nodes -days 3650 -newkey rsa:4096 \
 -keyout certificates/web_certificates/iris.key \
 -out certificates/web_certificates/iris.crt \
 -subj "/C=IN/ST=TN/L=Chennai/O=DFIR/CN=iris.local"

cp certificates/web_certificates/iris.crt certificates/rootCA/irisRootCACert.pem
```

### Step 3 — Set Environment Variables

> ⚠️ **CRITICAL — Two common mistakes that kill the worker:**
> 1. Using `IRIS_SECRET_KEY` instead of `SECRET_KEY` → `SECRET_KEY = None` → `TypeError: encoding without a string argument`
> 2. Setting `SERVER_NAME` in `.env` → nginx reads it to build `upstream app:<port>` → `invalid port in upstream ':'`

```bash
cp .env.example .env

# Auto-generate secrets
SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
SALT=$(python3 -c "import secrets; print(secrets.token_hex(16))")
DBPASS="IrisDB$(openssl rand -hex 8)"

sed -i "s|CHANGE_ME_secret_key_min_32_chars|${SECRET}|g" .env
sed -i "s|CHANGE_ME_password_salt|${SALT}|g" .env
sed -i "s|CHANGE_ME_db_password|${DBPASS}|g" .env
sed -i "s|^DB_PASS=.*|DB_PASS=${DBPASS}|" .env

# Verify — must show values, NOT 'CHANGE_ME'
grep -E '^SECRET_KEY=|^SECURITY_PASSWORD_SALT=|^DB_PASS=|^DB_HOST=' .env
```

### Step 4 — Start the Stack

```bash
# Elasticsearch kernel requirement (must do BEFORE compose up)
sudo sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf

# Create cortex dirs with correct permissions
mkdir -p cortex/logs cortex/config cortex/neurons
chmod 777 cortex/logs

docker compose up -d
docker compose logs -f --tail=20
```

### Step 5 — Verify Services

```bash
# All containers must show healthy or running
docker compose ps

# Individual health checks
curl -sk https://localhost/api/ping | python3 -m json.tool
curl -s http://localhost:9001/cortex/api/status | python3 -m json.tool
curl -s http://localhost:9200/_cat/health

# Worker must show 'celery@xxxx ready.' with no errors
docker compose logs worker --tail=20 | grep -E 'ready|ERROR|Secret'
```

### Step 6 — Set Up Cortex

1. Open `http://<YOUR_IP>:9001` → **Update Database** → wait
2. Create admin user → login
3. **Organization** → **Create Org** (e.g. `IRIS`)
4. Switch to org → **Users** → **Create User** → Role: `orgAdmin`
5. Click user → **API Keys** → **Create** → **Copy the key** ← needed next
6. **Analyzers** → Enable the ones you want (e.g. `VirusTotal_GetReport_3_1`)

> ⚠️ Cortex 4.x API path is `/cortex/api/...` not `/api/...`. The IrisCortexModule v3 auto-detects this.

### Step 7 — Install the IRIS Cortex Module

Must install in **both** `app` and `worker` containers:

```bash
docker exec iriswebapp_app pip install --upgrade \
 'git+https://github.com/Ramkumar2545/dfir-iris-cortex-stack.git#subdirectory=iris_module'

docker exec iriswebapp_worker pip install --upgrade \
 'git+https://github.com/Ramkumar2545/dfir-iris-cortex-stack.git#subdirectory=iris_module'

docker compose restart app worker

# Verify
docker exec iriswebapp_app pip show iris-cortex-module-v3
docker exec iriswebapp_worker pip show iris-cortex-module-v3
```

### Step 8 — Configure Module in IRIS UI

1. `https://<YOUR_IP>` → **Advanced** → **Modules**
2. **➕ Add Module** → class name: `IrisCortexModuleV3` → **Enable**
3. **⚙️ Configure**:

| Parameter | Value | Notes |
|---|---|---|
| `cortex_url` | `http://<YOUR_IP>:9001` | Module auto-detects `/cortex` path |
| `cortex_api_key` | *(from Step 6)* | orgAdmin API key |
| `cortex_analyzers` | `VirusTotal_GetReport_3_1` | One per line |
| `auto_select_analyzers` | `false` | |
| `report_as_attribute` | `true` | |
| `job_timeout_seconds` | `300` | |
| `verify_ssl` | `false` | |

4. **Save** → green ✅ toast = success

### Step 9 — Test End-to-End

```bash
docker compose logs worker -f 2>&1 | grep -iE 'cortex|ioc|hook|saved|error'
```

In IRIS: **Cases** → open/create case → **IOCs** → add `8.8.8.8` (type `ip`) → right-click → **Run Cortex Analyzers v3**

Expected worker log:
```
[IrisCortex v3] Hook fired: on_manual_trigger_ioc
[IrisCortex v3] Client → http://192.168.31.144:9001/cortex
[IrisCortex v3] IOC='8.8.8.8' | IRIS=ip | Cortex=ip
[IrisCortex v3] ▶ VirusTotal_GetReport_3_1 ← '8.8.8.8' (ip)
[IrisCortex v3] Job finished: Success
[IrisCortex v3] ✔ Saved: CORTEX v3: VirusTotal_GetReport_3_1
```

---

## Known Issues & Fixes

### ❌ Issue 1: `invalid port in upstream ':'` (nginx crash loop)

**Symptom:**
```
nginx: [emerg] invalid port in upstream ":" in /etc/nginx/nginx.conf:123
```

**Root Cause:** The IRIS nginx image uses `SERVER_NAME` from the environment to build its upstream block: `upstream app { server $SERVER_NAME:8000; }`. If `SERVER_NAME` is set to a hostname only (without `:port`), or is blank, nginx parses it as `":"` → invalid port.

The `.env` file had `SERVER_NAME=iris.local` which the nginx container inherited via `env_file:` — nginx tried to use `iris.local` as the upstream but then couldn't find the port separately, resulting in `upstream ":"` at line 123.

**Fix:** Remove `SERVER_NAME` from `.env` and from `env_file:` on the nginx service. Set it directly in `environment:` in `docker-compose.yml`:
```yaml
iriswebapp_nginx:
  environment:
    - SERVER_NAME=iriswebapp_app   # container name = Docker DNS name
    - IRIS_UPSTREAM_PORT=8000
  # No env_file: here — avoid inheriting SERVER_NAME from .env
```

---

### ❌ Issue 2: `chown: changing ownership of '/etc/cortex': Read-only file system`

**Symptom:**
```
chown: changing ownership of '/etc/cortex/application.conf': Read-only file system
chown: changing ownership of '/etc/cortex': Read-only file system
```

**Root Cause:** The Cortex container entrypoint script runs `chown -R cortex /etc/cortex` on startup to take ownership of config files. This is by design — but we had the volume mounted as `:ro` (read-only):
```yaml
- ./cortex/config:/etc/cortex:ro   # WRONG — entrypoint needs to chown
```

**Fix:** Remove `:ro` flag from the cortex config mount:
```yaml
- ./cortex/config:/etc/cortex      # No :ro — entrypoint can chown
```

---

### ❌ Issue 3: `FileNotFoundException: /etc/cortex/logback.xml` (Cortex won't start)

**Symptom:**
```
ch.qos.logback.core.joran.spi.JoranException: Could not open URL [file:/etc/cortex/logback.xml]
Caused by: java.io.FileNotFoundException: /etc/cortex/logback.xml (No such file or directory)
Oops, cannot start the server.
```

**Root Cause:** Cortex's Play Framework looks for a custom `logback.xml` at `/etc/cortex/logback.xml`. We only provided `application.conf` in `./cortex/config/` — the `logback.xml` file was missing entirely.

**Fix:** Add `cortex/config/logback.xml` to the repo (already included). This file is now mounted into `/etc/cortex/logback.xml` and redirects logs to both stdout and `/var/log/cortex/application.log`.

---

### ❌ Issue 4: `Permission denied` on `/var/log/cortex/application.log`

**Symptom:**
```
openFile(/var/log/cortex/application.log,true) call failed.
java.io.FileNotFoundException: /var/log/cortex/application.log (Permission denied)
```

**Root Cause:** Docker creates the host directory `./cortex/logs` owned by `root:root` with `755`. The Cortex process (uid 1001) cannot write to it.

**Fix:** `scripts/setup.sh` now runs `chmod 777 cortex/logs` before compose up. Or manually:
```bash
mkdir -p cortex/logs && chmod 777 cortex/logs
```

---

### ❌ Issue 5: `TypeError: encoding without a string argument` (worker crash)

**Root Cause:** `.env` used `IRIS_SECRET_KEY` instead of `SECRET_KEY`. IRIS reads `SECRET_KEY` directly — prefixed name returns `None`. Fix: rename in `.env`.

```bash
VAL=$(grep '^IRIS_SECRET_KEY=' .env | cut -d'=' -f2-)
sed -i '/^IRIS_SECRET_KEY=/d' .env
echo "SECRET_KEY=${VAL}" >> .env
docker compose down && docker compose up -d
```

---

### ❌ Issue 6: `cortex4py` incompatible with Cortex 4.x

**Root Cause:** `cortex4py 2.x` targets `/api/...`. Cortex 4.x uses `/cortex/api/...`. The IrisCortexModule v3 replaces `cortex4py` with native `requests` and auto-detects the path.

---

### ❌ Issue 7: `Unable to update hooks` in IRIS UI

**Root Cause:** Module installed only in `worker` — IRIS registers hooks from `app`. Install in both containers (see Step 7).

---

### ❌ Issue 8: Elasticsearch `vm.max_map_count` too low

```bash
sudo sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf
docker compose restart elasticsearch
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
| `elasticsearch` | 3 GB | Heap: `-Xms1g -Xmx2g` |
| `iris app` | 2 GB | WebApp + uWSGI |
| `cortex` | 2 GB | Heap: `-Xms1g -Xmx1g` |
| `iris worker` | 1 GB | Celery |
| `db` | 1 GB | PostgreSQL |
| `rabbitmq` | 512 MB | Message broker |
| `nginx` | 256 MB | Reverse proxy |

---

## Troubleshooting

```bash
# Worker not starting
docker exec iriswebapp_worker env | grep -E 'SECRET_KEY|SECURITY_PASSWORD'
docker compose logs worker --tail=50

# Cortex not starting
docker compose logs cortex --tail=50
ls -la cortex/config/   # must contain application.conf AND logback.xml
ls -la cortex/logs/     # must be chmod 777

# Nginx crash loop
docker compose logs iriswebapp_nginx --tail=10
# If you see 'invalid port in upstream' — check nginx has no env_file pointing to .env

# Module not in IRIS UI
docker exec iriswebapp_app pip show iris-cortex-module-v3
docker compose logs app --tail=30 | grep -iE 'cortex|module|error'

# Full reset (WARNING: deletes all data)
docker compose down -v && docker compose up -d
```

---

## License

MIT — see [LICENSE](LICENSE)

---

> Built and battle-tested by [@Ramkumar2545](https://github.com/Ramkumar2545)
