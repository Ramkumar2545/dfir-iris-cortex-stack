#!/usr/bin/env python3
"""
IRIS Cortex Module v3 — Core Handler

Key design decisions:
  1. Native requests — no cortex4py (cortex4py 2.x is Cortex 3.x only)
  2. Auto-detects Cortex 4.x sub-path (/cortex/api) vs 3.x (/api)
  3. safe_str() on all IOC values — prevents encoding errors
  4. No Flask app context dependencies — safe in Celery worker
  5. Python 3.9+ compatible
"""

from __future__ import annotations

import json
import time
from typing import Any, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from jinja2 import Environment, BaseLoader, TemplateError


IOC_TYPE_MAP: dict[str, str] = {
    "ip": "ip",          "ip-src": "ip",       "ip-dst": "ip",
    "ipv4": "ip",        "ipv6": "ip",          "ip-any": "ip",
    "ip-src|port": "ip", "ip-dst|port": "ip",  "ip|port": "ip",
    "domain": "domain",  "fqdn": "domain",     "hostname": "domain",
    "domain|ip": "domain", "hostname|port": "domain", "domain|port": "domain",
    "url": "url",        "uri": "url",          "link": "url",
    "md5": "hash",       "sha1": "hash",        "sha224": "hash",
    "sha256": "hash",    "sha384": "hash",       "sha512": "hash",
    "ssdeep": "hash",    "tlsh": "hash",         "imphash": "hash",
    "authentihash": "hash", "sha3-256": "hash", "sha3-512": "hash",
    "filename|md5": "hash",   "filename|sha1": "hash",
    "filename|sha256": "hash", "filename|sha512": "hash",
    "email": "mail",     "mail": "mail",         "email-src": "mail",
    "email-dst": "mail",
    "filename": "filename", "filepath": "filename", "file": "filename",
    "regkey": "registry", "registry": "registry",
    "user-agent": "user-agent",
    "asn": "autonomous-system", "as": "autonomous-system",
    "mac-address": "mac-address", "mac": "mac-address",
    "vulnerability": "other", "cve": "other",
    "text": "other",     "comment": "other",      "other": "other",
}

TYPE_PRIORITY: List[str] = [
    "ip", "domain", "hash", "url", "mail",
    "filename", "registry", "user-agent",
    "autonomous-system", "mac-address", "other",
]


def safe_str(value: Any) -> str:
    """Convert any value IRIS may pass (None, bytes, ORM obj) to plain str."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return repr(value)


def safe_attr(obj: Any, *attrs: str, default: Any = None) -> Any:
    current = obj
    for attr in attrs:
        if current is None:
            return default
        try:
            result = getattr(current, attr, None)
            if result is None and isinstance(current, dict):
                result = current.get(attr)
            current = result
        except Exception:
            return default
    return current if current is not None else default


class CortexClient:
    """
    Thin HTTP client for Cortex REST API.
    Auto-detects:
      Cortex 4.x → base_url/cortex/api/...
      Cortex 3.x → base_url/api/...
    """

    def __init__(self, base_url: str, api_key: str, verify_ssl: bool = False):
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        self.base_url = self._detect_base(base_url.rstrip("/"))

        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })
        retry = Retry(total=3, backoff_factor=1,
                      status_forcelist=[429, 500, 502, 503, 504])
        self._session.mount("http://",  HTTPAdapter(max_retries=retry))
        self._session.mount("https://", HTTPAdapter(max_retries=retry))

    def _detect_base(self, url: str) -> str:
        if url.endswith("/cortex"):
            return url
        # Probe Cortex 4.x path
        try:
            r = requests.get(
                f"{url}/cortex/api/status", timeout=5,
                verify=False,
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            if r.status_code == 200 and "Cortex" in r.text:
                return f"{url}/cortex"
        except Exception:
            pass
        return url  # Cortex 3.x fallback

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/{path.lstrip('/')}"

    def _get(self, path: str) -> Any:
        r = self._session.get(self._url(path), verify=self.verify_ssl, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> Any:
        r = self._session.post(self._url(path), json=body,
                               verify=self.verify_ssl, timeout=30)
        r.raise_for_status()
        return r.json()

    def analyzers_for_type(self, data_type: str) -> List[str]:
        try:
            result = self._get(f"analyzer/type/{data_type}")
            return [a.get("name", "") for a in result if a.get("name")]
        except Exception:
            return []

    def run_analyzer(self, name: str, value: str, data_type: str, tlp: int = 2) -> str:
        body = {"data": value, "dataType": data_type, "tlp": tlp,
                "message": "Triggered by IRIS Cortex Module v3"}
        result = self._post(f"analyzer/{name}/run", body)
        job_id = result.get("id") or result.get("_id")
        if not job_id:
            raise ValueError(f"No job ID in response: {result}")
        return job_id

    def get_job(self, job_id: str) -> dict:
        return self._get(f"job/{job_id}")

    def get_job_report(self, job_id: str) -> dict:
        try:
            return self._get(f"job/{job_id}/report")
        except Exception:
            return {}


class CortexHandler:
    def __init__(self, cortex_url: str, cortex_api_key: str,
                 mod_config: dict, logger: Any):
        self.cortex_url = cortex_url.rstrip("/")
        self.cortex_api_key = cortex_api_key
        self.mod_config = mod_config
        self.log = logger
        self._client: Optional[CortexClient] = None

    def _cf(self, *keys: str, default: Any = None) -> Any:
        for k in keys:
            v = self.mod_config.get(k)
            if v is not None:
                return v
        return default

    def _get_client(self) -> CortexClient:
        if self._client is None:
            verify = bool(self._cf("verify_ssl", default=False))
            self._client = CortexClient(self.cortex_url, self.cortex_api_key, verify)
            self.log.info(f"[IrisCortex v3] Client → {self._client.base_url}")
        return self._client

    def _resolve_type(self, raw: str) -> str:
        t = safe_str(raw).lower().strip()
        if t in IOC_TYPE_MAP:
            return IOC_TYPE_MAP[t]
        if "|" in t:
            hits = [IOC_TYPE_MAP[p] for p in t.split("|") if p.strip() in IOC_TYPE_MAP]
            for pref in TYPE_PRIORITY:
                if pref in hits:
                    return pref
        self.log.warning(f"[IrisCortex v3] Unknown type '{raw}' → other")
        return "other"

    def _configured_analyzers(self) -> List[str]:
        raw = safe_str(self._cf("cortex_analyzers", default=""))
        return [p.strip() for p in raw.replace("\n", ",").split(",") if p.strip()]

    def _run_and_wait(self, client: CortexClient, name: str,
                      value: str, dtype: str) -> dict:
        timeout = int(self._cf("job_timeout_seconds", default=300))
        poll    = int(self._cf("poll_interval_seconds", default=5))

        self.log.info(f"[IrisCortex v3] ▶ {name} ← '{value}' ({dtype})")
        try:
            job_id = client.run_analyzer(name, value, dtype)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return {"error": f"Analyzer '{name}' not found or not enabled in Cortex"}
            return {"error": str(exc)}

        self.log.info(f"[IrisCortex v3] Job: {job_id}")
        elapsed, status = 0, "Waiting"
        while elapsed < timeout:
            try:
                job = client.get_job(job_id)
                status = job.get("status", "Waiting")
                if status in ("Success", "Failure"):
                    break
            except Exception as exc:
                self.log.warning(f"[IrisCortex v3] Poll error: {exc}")
            time.sleep(poll)
            elapsed += poll

        self.log.info(f"[IrisCortex v3] Job {job_id} → {status}")
        if status == "Success":
            r = client.get_job_report(job_id)
            full = r.get("report", {}).get("full") or r.get("full") or r
            return full if isinstance(full, dict) else {"result": full}
        elif status == "Failure":
            r = client.get_job_report(job_id)
            err = (r.get("report", {}).get("errorMessage")
                   or r.get("errorMessage")
                   or r.get("error", "Analyzer job failed"))
            return {"error": safe_str(err)}
        return {"error": f"Timeout after {timeout}s (last status: {status})"}

    def _render(self, results: dict, name: str, value: str, dtype: str) -> str:
        tmpl_str = safe_str(self._cf(
            "report_template",
            default="<pre style='white-space:pre-wrap;word-break:break-all;'>{{ results | tojson(indent=2) }}</pre>"
        ))
        try:
            env = Environment(loader=BaseLoader())
            env.filters["tojson"] = lambda v, indent=None: json.dumps(v, indent=indent, default=str)
            return env.from_string(tmpl_str).render(
                results=results, analyzer_name=name, ioc_value=value, data_type=dtype)
        except TemplateError as exc:
            self.log.warning(f"[IrisCortex v3] Template error: {exc}")
            return f"<pre>{json.dumps(results, indent=2, default=str)}</pre>"

    def _save(self, ioc: Any, name: str, html: str) -> None:
        attr = f"CORTEX v3: {name}"
        if hasattr(ioc, "add_attribute"):
            try:
                ioc.add_attribute(attribute_name=attr, attribute_value=html)
                self.log.info(f"[IrisCortex v3] ✔ Saved: {attr}")
                return
            except Exception as exc:
                self.log.warning(f"[IrisCortex v3] add_attribute failed: {exc}")
        try:
            attrs = getattr(ioc, "ioc_custom_attributes", None) or {}
            if isinstance(attrs, dict):
                attrs[attr] = html
                ioc.ioc_custom_attributes = attrs
                self.log.info(f"[IrisCortex v3] ✔ Saved via dict: {attr}")
                return
        except Exception as exc:
            self.log.warning(f"[IrisCortex v3] dict fallback failed: {exc}")
        self.log.warning(f"[IrisCortex v3] Could not persist '{attr}'")

    def handle_iocs(self, data: Any) -> None:
        client = self._get_client()
        if data is None:
            self.log.warning("[IrisCortex v3] No IOC data")
            return
        if not isinstance(data, (list, tuple)):
            data = [data]

        analyzers   = self._configured_analyzers()
        auto_select = bool(self._cf("auto_select_analyzers", default=False))
        save_report = bool(self._cf("report_as_attribute",   default=True))

        for ioc in data:
            value = safe_str(
                safe_attr(ioc, "ioc_value") or
                safe_attr(ioc, "value") or
                (ioc.get("ioc_value") if isinstance(ioc, dict) else None) or ""
            ).strip()

            if not value:
                self.log.warning("[IrisCortex v3] Empty IOC — skipping")
                continue

            raw_type  = safe_str(
                safe_attr(ioc, "ioc_type", "type_name") or
                safe_attr(ioc, "ioc_type") or
                (ioc.get("ioc_type") if isinstance(ioc, dict) else None) or "other"
            )
            dtype = self._resolve_type(raw_type)
            self.log.info(f"[IrisCortex v3] IOC={value!r} | IRIS={raw_type} | Cortex={dtype}")

            active = client.analyzers_for_type(dtype) or analyzers if auto_select else analyzers
            if not active:
                self.log.warning(f"[IrisCortex v3] No analyzers for '{value}'")
                continue

            for aname in active:
                aname = safe_str(aname).strip()
                if not aname:
                    continue
                try:
                    results = self._run_and_wait(client, aname, value, dtype)
                    if save_report:
                        html = self._render(results, aname, value, dtype)
                        self._save(ioc, aname, html)
                except Exception as exc:
                    self.log.error(f"[IrisCortex v3] {aname}/{value!r}: {exc}", exc_info=True)
