"""Motor genérico y reutilizable de aprovisionamiento de cables en NetBox.

Permite procesar especificaciones de cableado L1/L2 desde ficheros declarativos
de cualquier sede, resolviendo interfaces, validando precondiciones e ingestando
cables de forma estrictamente idempotente.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from netbox_core.client import NetBoxClient

logger = logging.getLogger(__name__)


class CableProvisioner:
    """Aprovisionador genérico de cableado e interfaces en NetBox."""

    def __init__(self, client: Optional[NetBoxClient] = None):
        self.client = client or NetBoxClient()
        self._device_cache: Dict[str, Dict[str, Any]] = {}
        self._interface_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def load_specification(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Carga y valida sintácticamente el fichero de especificación JSON."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Fichero de especificación no encontrado: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "cables" not in data or not isinstance(data["cables"], list):
            raise ValueError(f"El fichero {path.name} debe contener una lista 'cables'.")

        return data

    def get_device(self, device_name: str, site_name: Optional[str] = None) -> Dict[str, Any]:
        """Obtiene un dispositivo por nombre con caché local."""
        cache_key = f"{site_name}:{device_name}" if site_name else device_name
        if cache_key in self._device_cache:
            return self._device_cache[cache_key]

        params: Dict[str, Any] = {"name": device_name}
        res = self.client.get("dcim/devices", params=params)
        results = res.get("results", [])

        if not results:
            raise ValueError(f"Dispositivo no encontrado en NetBox: '{device_name}'")

        if len(results) > 1 and site_name:
            matched = [d for d in results if d.get("site", {}).get("name") == site_name]
            if matched:
                results = matched

        device = results[0]
        self._device_cache[cache_key] = device
        return device

    def resolve_interface(
        self,
        device_name: str,
        intf_name: str,
        site_name: Optional[str] = None,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        """Resuelve el objeto interfaz de un dispositivo en NetBox."""
        cache_key = (device_name, intf_name)
        if not refresh and cache_key in self._interface_cache:
            return self._interface_cache[cache_key]

        dev = self.get_device(device_name, site_name=site_name)
        dev_id = dev["id"]

        res = self.client.get("dcim/interfaces", params={"device_id": dev_id, "name": intf_name})
        results = res.get("results", [])

        if not results:
            raise ValueError(f"Interfaz '{intf_name}' no encontrada en el dispositivo '{device_name}' (ID: {dev_id})")

        intf = results[0]
        self._interface_cache[cache_key] = intf
        return intf

    def ensure_interfaces(
        self,
        interfaces_spec: List[Dict[str, Any]],
        site_name: Optional[str] = None,
        dry_run: bool = False,
    ) -> List[Dict[str, Any]]:
        """Garantiza la pre-existencia de interfaces físicas declaradas."""
        actions: List[Dict[str, Any]] = []

        for item in interfaces_spec:
            dev_name = item.get("device")
            intf_name = item.get("name")
            intf_type = item.get("type", "1000base-t")
            desc = item.get("description", "")

            if not dev_name or not intf_name:
                continue

            dev = self.get_device(dev_name, site_name=site_name)
            dev_id = dev["id"]

            try:
                existing = self.resolve_interface(dev_name, intf_name, site_name=site_name)
                actions.append({
                    "action": "EXISTS",
                    "device": dev_name,
                    "interface": intf_name,
                    "id": existing["id"],
                })
            except ValueError:
                # No existe, debe crearse
                if dry_run:
                    actions.append({
                        "action": "PLANNED_CREATE",
                        "device": dev_name,
                        "interface": intf_name,
                        "type": intf_type,
                        "description": desc,
                    })
                else:
                    payload = {
                        "device": dev_id,
                        "name": intf_name,
                        "type": intf_type,
                        "description": desc,
                    }
                    new_intf = self.client.post("dcim/interfaces", payload)
                    self._interface_cache[(dev_name, intf_name)] = new_intf
                    actions.append({
                        "action": "CREATED",
                        "device": dev_name,
                        "interface": intf_name,
                        "id": new_intf.get("id"),
                    })

        return actions

    def provision_cables(
        self,
        spec: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Procesa y ejecuta la provisión completa de cables a partir de la especificación."""
        site_name = spec.get("site")
        ensure_spec = spec.get("ensure_interfaces", [])
        cables_spec = spec.get("cables", [])

        summary: Dict[str, List[Dict[str, Any]]] = {
            "interfaces_ensured": [],
            "created": [],
            "skipped": [],
            "conflicts": [],
            "errors": [],
        }

        # 1. Asegurar interfaces requeridas
        if ensure_spec:
            summary["interfaces_ensured"] = self.ensure_interfaces(
                ensure_spec, site_name=site_name, dry_run=dry_run
            )

        # 2. Procesar cada cable
        for idx, cable_item in enumerate(cables_spec, start=1):
            side_a = cable_item.get("side_a", {})
            side_b = cable_item.get("side_b", {})
            c_type = cable_item.get("type", "cat6")
            c_status = cable_item.get("status", "connected")
            label = cable_item.get("label", "")
            desc = cable_item.get("description", "")

            dev_a = side_a.get("device")
            intf_a_name = side_a.get("interface")
            dev_b = side_b.get("device")
            intf_b_name = side_b.get("interface")

            endpoint_repr = f"{dev_a}:{intf_a_name} <--> {dev_b}:{intf_b_name}"

            try:
                # En modo dry-run, si la interfaz fue 'PLANNED_CREATE', simulamos
                intf_a_id = None
                intf_b_id = None

                try:
                    intf_a = self.resolve_interface(dev_a, intf_a_name, site_name=site_name)
                    intf_a_id = intf_a["id"]
                except ValueError as e:
                    if dry_run and any(
                        act["device"] == dev_a and act["interface"] == intf_a_name
                        for act in summary["interfaces_ensured"]
                    ):
                        intf_a = {"id": -1, "cable": None}
                    else:
                        raise e

                try:
                    intf_b = self.resolve_interface(dev_b, intf_b_name, site_name=site_name)
                    intf_b_id = intf_b["id"]
                except ValueError as e:
                    if dry_run and any(
                        act["device"] == dev_b and act["interface"] == intf_b_name
                        for act in summary["interfaces_ensured"]
                    ):
                        intf_b = {"id": -2, "cable": None}
                    else:
                        raise e

                # Comprobación de idempotencia: ¿tienen cable conectado?
                cable_a = intf_a.get("cable")
                cable_b = intf_b.get("cable")

                if cable_a and cable_b and cable_a.get("id") == cable_b.get("id"):
                    summary["skipped"].append({
                        "cable_idx": idx,
                        "endpoints": endpoint_repr,
                        "cable_id": cable_a.get("id"),
                        "reason": "Cable ya existente y conectado entre ambos extremos.",
                    })
                    continue

                if cable_a or cable_b:
                    summary["conflicts"].append({
                        "cable_idx": idx,
                        "endpoints": endpoint_repr,
                        "cable_a": cable_a,
                        "cable_b": cable_b,
                        "reason": "Uno de los extremos ya tiene otro cable asignado en NetBox.",
                    })
                    continue

                # Proceder a planificar o crear
                if dry_run:
                    summary["created"].append({
                        "cable_idx": idx,
                        "endpoints": endpoint_repr,
                        "status": "PLANNED",
                        "type": c_type,
                        "label": label,
                        "description": desc,
                    })
                else:
                    payload = {
                        "a_terminations": [{"object_type": "dcim.interface", "object_id": intf_a_id}],
                        "b_terminations": [{"object_type": "dcim.interface", "object_id": intf_b_id}],
                        "type": c_type,
                        "status": c_status,
                        "label": label,
                        "description": desc,
                    }
                    res = self.client.post("dcim/cables", payload)
                    cable_id = res.get("id")

                    # Actualizar caché de cables en las interfaces
                    intf_a["cable"] = {"id": cable_id}
                    intf_b["cable"] = {"id": cable_id}

                    summary["created"].append({
                        "cable_idx": idx,
                        "endpoints": endpoint_repr,
                        "status": "CREATED",
                        "cable_id": cable_id,
                        "label": label,
                        "description": desc,
                    })

            except Exception as e:
                summary["errors"].append({
                    "cable_idx": idx,
                    "endpoints": endpoint_repr,
                    "error": str(e),
                })

        return summary
