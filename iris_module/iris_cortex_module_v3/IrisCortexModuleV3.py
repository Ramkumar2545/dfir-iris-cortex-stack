#!/usr/bin/env python3
"""
IrisCortexModule v3 — DFIR-IRIS module class
Registers hooks and dispatches to the core handler.

Compatible with: IRIS 2.x, Cortex 3.x and 4.x, Python 3.9+
No cortex4py dependency — uses native requests.
"""

from __future__ import annotations

import traceback
from typing import Any, List

from iris_interface.IrisModuleInterface import (
    IrisModuleInterface, IrisModuleTypes
)
import iris_interface.IrisInterfaceStatus as InterfaceStatus

from .cortex.handler import CortexHandler


mod_description = "Cortex Analyzer integration for DFIR-IRIS. Supports Cortex 3.x and 4.x."

mod_config = [
    {
        "param_name": "cortex_url",
        "param_human_name": "Cortex URL",
        "param_description": "Base URL of your Cortex instance. e.g. http://192.168.1.100:9001",
        "default": "http://cortex:9001",
        "mandatory": True,
        "type": "string",
    },
    {
        "param_name": "cortex_api_key",
        "param_human_name": "Cortex API Key",
        "param_description": "API key from Cortex UI → Organization → Users → API Keys",
        "default": "",
        "mandatory": True,
        "type": "sensitive_string",
    },
    {
        "param_name": "cortex_analyzers",
        "param_human_name": "Analyzers",
        "param_description": "Analyzer names (one per line or comma-separated). e.g. VirusTotal_GetReport_3_1",
        "default": "VirusTotal_GetReport_3_1",
        "mandatory": False,
        "type": "textfield",
    },
    {
        "param_name": "auto_select_analyzers",
        "param_human_name": "Auto-select analyzers by IOC type",
        "param_description": "If true, queries Cortex for analyzers compatible with the IOC data type.",
        "default": False,
        "mandatory": False,
        "type": "bool",
    },
    {
        "param_name": "report_as_attribute",
        "param_human_name": "Save report as IOC attribute",
        "param_description": "Save the Cortex report as a custom attribute on the IOC.",
        "default": True,
        "mandatory": False,
        "type": "bool",
    },
    {
        "param_name": "verify_ssl",
        "param_human_name": "Verify SSL",
        "param_description": "Verify Cortex TLS certificate. Set false for self-signed certs.",
        "default": False,
        "mandatory": False,
        "type": "bool",
    },
    {
        "param_name": "job_timeout_seconds",
        "param_human_name": "Job timeout (seconds)",
        "param_description": "Max seconds to wait for each analyzer job to complete.",
        "default": 300,
        "mandatory": False,
        "type": "int",
    },
    {
        "param_name": "poll_interval_seconds",
        "param_human_name": "Poll interval (seconds)",
        "param_description": "Seconds between Cortex job status polls.",
        "default": 5,
        "mandatory": False,
        "type": "int",
    },
    {
        "param_name": "report_template",
        "param_human_name": "Report HTML template",
        "param_description": "Jinja2 template. Variables: results, analyzer_name, ioc_value, data_type.",
        "default": "<pre style='white-space:pre-wrap;word-break:break-all;'>{{ results | tojson(indent=2) }}</pre>",
        "mandatory": False,
        "type": "textfield",
    },
]


class IrisCortexModuleV3(IrisModuleInterface):
    _module_name        = "IrisCortexModuleV3"
    _module_description = mod_description
    _module_version     = "3.0.0"
    # _interface_version must match the iris-module-interface package version
    # installed in the container. iris_interface 1.1.0 is shipped with IRIS 2.x.
    _interface_version  = 1.1
    _module_type        = IrisModuleTypes.module_processor
    _module_configuration = mod_config
    _module_tags        = ["Cortex", "Analyzer", "Threat Intelligence"]
    _is_active          = True

    def __init__(self):
        super().__init__()
        self.register_to_hook(module_name=self._module_name,
                               iris_hook_name="on_postload_ioc_create")
        self.register_to_hook(module_name=self._module_name,
                               iris_hook_name="on_postload_ioc_update")

    def hooks_handler(self, hook_name: str, hook_ui_name: str, data: Any):
        """Called by IRIS Celery worker for every registered hook event."""
        self.log.info(f"[IrisCortex v3] Hook fired: {hook_name}")
        try:
            handler = CortexHandler(
                cortex_url=self._mod_config_string("cortex_url"),
                cortex_api_key=self._mod_config_string("cortex_api_key"),
                mod_config=self._mod_config_dict(),
                logger=self.log,
            )
            handler.handle_iocs(data)
        except Exception:
            self.log.error(
                f"[IrisCortex v3] hooks_handler error:\n{traceback.format_exc()}"
            )
        return InterfaceStatus.I2Success()

    def _mod_config_string(self, key: str, default: str = "") -> str:
        val = self._mod_config.get(key, default)
        if val is None:
            return default
        return str(val)

    def _mod_config_dict(self) -> dict:
        try:
            if isinstance(self._mod_config, dict):
                return dict(self._mod_config)
            cfg: dict = {}
            for param in mod_config:
                k = param["param_name"]
                cfg[k] = getattr(self._mod_config, k,
                                  self._mod_config.get(k, param.get("default")))
            return cfg
        except Exception:
            return dict(self._mod_config) if isinstance(self._mod_config, dict) else {}

    def pipeline_handler(self, pipeline_type, pipeline_data):
        return InterfaceStatus.I2Success()

    def pipeline_files_handler(self, file_list: List[str]):
        return InterfaceStatus.I2Success()
