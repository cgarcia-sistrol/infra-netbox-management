"""Runner de conciliación e ingesta para túneles VPN B2B en NetBox.

Modelado exclusivo de túneles B2B (11 en HUB-00, 4 en HUB-02):
- Asignación de perfiles criptográficos creados:
    - ipsec-prof-b2b-axpo-dh19 (Axpo)
    - ipsec-prof-b2b-legacy-dh2 (Pascual-Gurb)
    - ipsec-prof-b2b-standard-dh14 (Resto de contrapartes)
- Grupo de túneles: VPNs-B2B-Extranet
- Nombres de túneles normalizados: <HUB>-<nombre_tunel> (ej. HUB00-to-Moeve)
- Terminaciones: dcim.interface enlazadas a la interfaz virtual en el firewall correspondiente.
- Tenants creados automáticamente para cada contraparte.
- Tags cruzados: b2b-remote, vpn:<slug-tunel>.
- Opción A: Relaciones IPAM multiobject hacia ipam.prefix:
    - local_prefixes: lista de prefijos locales enrutados en el túnel
    - remote_prefixes: lista de prefijos remotos alcanzables en VRF-B2B-EXT
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Set

from netbox_core.client import NetBoxClient

logger = logging.getLogger(__name__)

CATALOG_VPN_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "inputs",
    "firewall_vpn_tunnels_hub0_hub2.json",
)

TUNNEL_GROUP_B2B = {
    "name": "VPNs-B2B-Extranet",
    "slug": "vpns-b2b-extranet",
    "description": "Interconexiones IPsec Site-to-Site B2B con clientes, socios y plataformas externas",
}

TAG_B2B_REMOTE = {
    "name": "b2b-remote",
    "slug": "b2b-remote",
    "color": "3b82f6",
    "description": "Recurso asociado a conectividad B2B Site-to-Site externa",
}

CUSTOM_FIELDS_B2B = [
    {
        "name": "local_prefixes",
        "label": "Redes Locales Publicadas",
        "type": "multiobject",
        "object_types": ["vpn.tunnel"],
        "related_object_type": "ipam.prefix",
        "description": "Prefijos y subredes internas de Edison anunciadas a través del túnel VPN (Phase 2 Local)",
        "required": False,
        "ui_visible": "always",
        "ui_editable": "yes",
    },
    {
        "name": "remote_prefixes",
        "label": "Redes Remotas Publicadas",
        "type": "multiobject",
        "object_types": ["vpn.tunnel"],
        "related_object_type": "ipam.prefix",
        "description": "Prefijos y subredes remotas de la contraparte B2B alcanzables a través del túnel VPN (Phase 2 Remote)",
        "required": False,
        "ui_visible": "always",
        "ui_editable": "yes",
    },
]

CRYPTO_PROFILES = {
    "standard": "ipsec-prof-b2b-standard-dh14",
    "axpo": "ipsec-prof-b2b-axpo-dh19",
    "legacy": "ipsec-prof-b2b-legacy-dh2",
}

DEVICE_MAP = {
    "HUB-00": {"id": 8, "name": "FortiGate-100F", "prefix": "HUB00"},
    "HUB-02": {"id": 2, "name": "FGT100-JES", "prefix": "HUB02"},
}

VRF_B2B_ID = 1  # VRF-B2B-EXT
ROLE_B2B_NAT_ID = 13  # B2B Extranet / NAT
ROLE_FOTOVOLTAICA_ID = 16  # Fotovoltaica / Solar


def slugify(text: str) -> str:
    """Convierte texto en un slug normalizado."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text).strip("-")


def determine_crypto_profile(tunnel_name: str) -> str:
    """Selecciona el perfil criptográfico según la contraparte."""
    clean_name = tunnel_name.lower()
    if "axpo" in clean_name:
        return CRYPTO_PROFILES["axpo"]
    if "pascual-gurb" in clean_name:
        return CRYPTO_PROFILES["legacy"]
    return CRYPTO_PROFILES["standard"]


def extract_tenant_name(tunnel_name: str) -> str:
    """Extrae el nombre del Tenant para la contraparte a partir del nombre del túnel."""
    raw = tunnel_name
    if raw.startswith("to-"):
        raw = raw[3:]
    raw = raw.replace("-", " ").strip()
    return raw


class B2BVPNBatchRunner:
    """Ejecutor batch para modelado de túneles VPN B2B en NetBox."""

    def __init__(
        self,
        client: Optional[NetBoxClient] = None,
        catalog_path: str = CATALOG_VPN_PATH,
        dry_run: bool = True,
    ) -> None:
        self.client = client or NetBoxClient()
        self.catalog_path = catalog_path
        self.dry_run = dry_run
        self._crypto_profile_cache: Dict[str, int] = {}
        self._tenant_cache: Dict[str, int] = {}
        self._tag_cache: Dict[str, int] = {}
        self._prefix_cache: Dict[str, int] = {}

    def run(self, hub_filter: Optional[str] = None) -> Dict[str, Any]:
        """Ejecuta el proceso completo de conciliación e ingesta."""
        summary = {
            "tunnel_group": None,
            "custom_fields_ensured": 0,
            "tenants_created": 0,
            "prefixes_ensured": 0,
            "interfaces_created": 0,
            "tunnels_created": 0,
            "tunnels_updated": 0,
            "terminations_created": 0,
            "errors": [],
        }

        with open(self.catalog_path, "r", encoding="utf-8") as f:
            catalog = json.load(f)

        # 1. Asegurar Tunnel Group
        tg_id = self._ensure_tunnel_group()
        summary["tunnel_group"] = tg_id

        # 2. Asegurar Custom Fields de Relación IPAM
        summary["custom_fields_ensured"] = self._ensure_custom_fields()

        # 3. Asegurar Tag b2b-remote
        self._ensure_tag(TAG_B2B_REMOTE["name"], TAG_B2B_REMOTE["slug"], TAG_B2B_REMOTE["color"], TAG_B2B_REMOTE["description"])

        # 4. Cachear perfiles criptográficos
        self._cache_crypto_profiles()

        # 5. Procesar túneles B2B
        hubs_to_process = ["HUB-00", "HUB-02"]
        if hub_filter:
            hubs_to_process = [h for h in hubs_to_process if h == hub_filter]

        for hub_key in hubs_to_process:
            if hub_key not in catalog:
                continue

            device_info = DEVICE_MAP.get(hub_key)
            if not device_info:
                continue

            dev_id = device_info["id"]
            hub_prefix = device_info["prefix"]
            tunnels = [
                t for t in catalog[hub_key].get("tunnels", [])
                if t.get("group") == "B2B / Clientes"
            ]

            for t in tunnels:
                try:
                    res = self._process_b2b_tunnel(hub_key, hub_prefix, dev_id, tg_id, t)
                    if res.get("tenant_created"):
                        summary["tenants_created"] += 1
                    summary["prefixes_ensured"] += res.get("prefixes_ensured", 0)
                    if res.get("iface_created"):
                        summary["interfaces_created"] += 1
                    if res.get("tunnel_created"):
                        summary["tunnels_created"] += 1
                    elif res.get("tunnel_updated"):
                        summary["tunnels_updated"] += 1
                    if res.get("term_created"):
                        summary["terminations_created"] += 1
                except Exception as e:
                    logger.error(f"Error procesando {t['tunnel_name']} en {hub_key}: {e}")
                    summary["errors"].append({"hub": hub_key, "tunnel": t["tunnel_name"], "error": str(e)})

        return summary

    def _ensure_custom_fields(self) -> int:
        """Asegura la creación de los Custom Fields multiobject hacia ipam.prefix."""
        ensured = 0
        for cf in CUSTOM_FIELDS_B2B:
            res = self.client.get("extras/custom-fields", params={"name": cf["name"]})
            results = res.get("results", [])
            if results:
                ensured += 1
                continue

            if self.dry_run:
                logger.info(f"[DRY-RUN] Crear CustomField: {cf['name']} ({cf['label']})")
                ensured += 1
            else:
                self.client.post("extras/custom-fields", cf)
                logger.info(f"CustomField creado: {cf['name']}")
                ensured += 1
        return ensured

    def _ensure_tunnel_group(self) -> int:
        """Crea o resuelve el TunnelGroup VPNs-B2B-Extranet."""
        res = self.client.get("vpn/tunnel-groups", params={"slug": TUNNEL_GROUP_B2B["slug"]})
        results = res.get("results", [])
        if results:
            return results[0]["id"]

        if self.dry_run:
            logger.info(f"[DRY-RUN] Crear TunnelGroup: {TUNNEL_GROUP_B2B['name']}")
            return 99901

        created = self.client.post("vpn/tunnel-groups", TUNNEL_GROUP_B2B)
        return created["id"]

    def _ensure_tag(self, name: str, slug: str, color: str = "3b82f6", description: str = "") -> int:
        """Crea o resuelve un Tag en NetBox."""
        if slug in self._tag_cache:
            return self._tag_cache[slug]

        res = self.client.get("extras/tags", params={"slug": slug})
        results = res.get("results", [])
        if results:
            tag_id = results[0]["id"]
            self._tag_cache[slug] = tag_id
            return tag_id

        if self.dry_run:
            logger.info(f"[DRY-RUN] Crear Tag: {name} (slug: {slug})")
            mock_id = 99800 + len(self._tag_cache)
            self._tag_cache[slug] = mock_id
            return mock_id

        payload = {"name": name, "slug": slug, "color": color, "description": description}
        created = self.client.post("extras/tags", payload)
        tag_id = created["id"]
        self._tag_cache[slug] = tag_id
        return tag_id

    def _cache_crypto_profiles(self) -> None:
        """Recupera los IDs de los perfiles criptográficos B2B."""
        res = self.client.get("vpn/ipsec-profiles", params={"limit": 50})
        for item in res.get("results", []):
            self._crypto_profile_cache[item["name"]] = item["id"]

    def _ensure_tenant(self, tenant_name: str) -> Tuple[int, bool]:
        """Crea o resuelve el Tenant para la contraparte B2B."""
        tenant_slug = slugify(tenant_name)
        if tenant_slug in self._tenant_cache:
            return self._tenant_cache[tenant_slug], False

        res = self.client.get("tenancy/tenants", params={"slug": tenant_slug})
        results = res.get("results", [])
        if results:
            tid = results[0]["id"]
            self._tenant_cache[tenant_slug] = tid
            return tid, False

        if self.dry_run:
            logger.info(f"[DRY-RUN] Crear Tenant: {tenant_name} (slug: {tenant_slug})")
            mock_id = 99700 + len(self._tenant_cache)
            self._tenant_cache[tenant_slug] = mock_id
            return mock_id, True

        payload = {
            "name": tenant_name,
            "slug": tenant_slug,
            "description": f"Cliente / Socio B2B: {tenant_name}",
        }
        created = self.client.post("tenancy/tenants", payload)
        tid = created["id"]
        self._tenant_cache[tenant_slug] = tid
        return tid, True

    def _ensure_prefix(
        self,
        cidr: str,
        is_remote: bool,
        tenant_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
        description: str = "",
    ) -> int:
        """Resuelve o crea un prefijo en IPAM."""
        cache_key = f"{cidr}:{'remote' if is_remote else 'local'}"
        if cache_key in self._prefix_cache:
            return self._prefix_cache[cache_key]

        # 1. Búsqueda en NetBox
        query_params: Dict[str, Any] = {"prefix": cidr}
        if is_remote:
            query_params["vrf_id"] = VRF_B2B_ID
        res = self.client.get("ipam/prefixes", params=query_params)
        results = res.get("results", [])
        if results:
            pid = results[0]["id"]
            self._prefix_cache[cache_key] = pid
            return pid

        # Si es local y no se encontró por búsqueda estricta, buscar en global sin VRF
        if not is_remote:
            res_any = self.client.get("ipam/prefixes", params={"prefix": cidr})
            if res_any.get("results"):
                pid = res_any["results"][0]["id"]
                self._prefix_cache[cache_key] = pid
                return pid

        if self.dry_run:
            mock_id = 99400 + len(self._prefix_cache)
            self._prefix_cache[cache_key] = mock_id
            logger.info(f"[DRY-RUN] Crear Prefix IPAM: {cidr} (is_remote={is_remote})")
            return mock_id

        # 2. Creación del prefijo en NetBox
        role_id = ROLE_B2B_NAT_ID
        if not is_remote and cidr.startswith("172.20."):
            role_id = ROLE_FOTOVOLTAICA_ID

        payload: Dict[str, Any] = {
            "prefix": cidr,
            "status": "active",
            "description": description or ("Red remota B2B" if is_remote else "Red interna Edison"),
            "role": role_id,
        }
        if is_remote:
            payload["vrf"] = VRF_B2B_ID
            if tenant_id:
                payload["tenant"] = tenant_id
        if tag_ids:
            payload["tags"] = tag_ids

        created = self.client.post("ipam/prefixes", payload)
        pid = created["id"]
        self._prefix_cache[cache_key] = pid
        return pid

    def _ensure_virtual_interface(self, device_id: int, iface_name: str, tunnel_name: str) -> Tuple[int, bool]:
        """Asegura la existencia de la interfaz virtual para el túnel en el firewall."""
        res = self.client.get("dcim/interfaces", params={"device_id": device_id, "name": iface_name})
        results = res.get("results", [])
        if results:
            return results[0]["id"], False

        if self.dry_run:
            logger.info(f"[DRY-RUN] Crear Interfaz Virtual {iface_name} en Device ID {device_id}")
            return 99600 + device_id, True

        payload = {
            "device": device_id,
            "name": iface_name,
            "type": "virtual",
            "enabled": True,
            "description": f"Interfaz IPsec VPN {tunnel_name}",
        }
        created = self.client.post("dcim/interfaces", payload)
        return created["id"], True

    def _build_comments(self, tunnel_data: Dict[str, Any], hub_key: str, profile_name: str) -> str:
        """Construye documentación Markdown enriquecida para el túnel en NetBox."""
        lines = [
            f"## VPN Site-to-Site B2B: {tunnel_data['tunnel_name']}",
            f"- **Firewall**: {hub_key} ({DEVICE_MAP[hub_key]['name']})",
            f"- **Gateway Remoto (Peer)**: `{tunnel_data.get('remote_gw', 'N/A')}`",
            f"- **Interfaz WAN Origen**: `{tunnel_data.get('parent_interface', 'wan1')}`",
            f"- **Perfil Criptográfico**: `{profile_name}`",
            f"- **IKE Proposal (P1)**: `{tunnel_data.get('proposal_p1')} (DH: {tunnel_data.get('dhgrp_p1')})`",
            "",
            "### Selectores de Tráfico (Phase 2):",
        ]
        p2_list = tunnel_data.get("phase2_selectors", [])
        if p2_list:
            for p2 in p2_list:
                src_net = p2.get("src_effective_network")
                dst_net = p2.get("dst_effective_network")
                src_obj = p2.get("src-name") or p2.get("src_name") or p2.get("src-subnet") or "all"
                dst_obj = p2.get("dst-name") or p2.get("dst_name") or p2.get("dst-subnet") or "all"
                p2_prop = p2.get("proposal", "N/A")
                p2_dh = p2.get("dhgrp", "N/A")

                src_display = f"`{src_net}` (Obj: `{src_obj}`)" if src_net else f"`{src_obj}`"
                dst_display = f"`{dst_net}` (Obj: `{dst_obj}`)" if dst_net else f"`{dst_obj}`"

                lines.append(f"- **{p2.get('name')}**: {src_display} &rarr; {dst_display} | Crypto: `{p2_prop}` (DH: {p2_dh})")
        else:
            lines.append("- *(Sin selectores específicos configurados)*")

        return "\n".join(lines)

    def _process_b2b_tunnel(
        self,
        hub_key: str,
        hub_prefix: str,
        dev_id: int,
        tg_id: int,
        t_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Procesa e ingesta una instancia de túnel B2B en NetBox."""
        result = {
            "tenant_created": False,
            "prefixes_ensured": 0,
            "iface_created": False,
            "tunnel_created": False,
            "tunnel_updated": False,
            "term_created": False,
        }

        base_name = t_data["tunnel_name"]
        netbox_tunnel_name = f"{hub_prefix}-{base_name}"
        tunnel_slug = slugify(base_name)

        # 1. Tenant
        tenant_name = extract_tenant_name(base_name)
        tenant_id, tenant_created = self._ensure_tenant(tenant_name)
        result["tenant_created"] = tenant_created

        # 2. Tags
        tag_b2b_id = self._ensure_tag(TAG_B2B_REMOTE["name"], TAG_B2B_REMOTE["slug"])
        vpn_tag_slug = f"vpn-{tunnel_slug}"
        vpn_tag_name = f"vpn:{tunnel_slug}"
        tag_vpn_id = self._ensure_tag(vpn_tag_name, vpn_tag_slug, "06b6d4", f"VPN {base_name}")

        # 3. Interfaz Virtual
        iface_id, iface_created = self._ensure_virtual_interface(dev_id, base_name, netbox_tunnel_name)
        result["iface_created"] = iface_created

        # 4. Perfil Criptográfico
        profile_name = determine_crypto_profile(base_name)
        profile_id = self._crypto_profile_cache.get(profile_name)

        # 5. Resolver prefijos locales y remotos para Custom Fields multiobject
        local_prefix_ids: List[int] = []
        remote_prefix_ids: List[int] = []

        seen_local: Set[str] = set()
        seen_remote: Set[str] = set()

        for p2 in t_data.get("phase2_selectors", []):
            src_eff = p2.get("src_effective_network")
            dst_eff = p2.get("dst_effective_network")

            if src_eff and src_eff not in seen_local:
                seen_local.add(src_eff)
                pid = self._ensure_prefix(
                    cidr=src_eff,
                    is_remote=False,
                    tag_ids=[tag_vpn_id],
                    description=f"Red local publicada en VPN {netbox_tunnel_name}",
                )
                local_prefix_ids.append(pid)
                result["prefixes_ensured"] += 1

            if dst_eff and dst_eff not in seen_remote:
                seen_remote.add(dst_eff)
                pid = self._ensure_prefix(
                    cidr=dst_eff,
                    is_remote=True,
                    tenant_id=tenant_id,
                    tag_ids=[tag_b2b_id, tag_vpn_id],
                    description=f"Red remota de {tenant_name} alcanzable vía VPN {netbox_tunnel_name}",
                )
                remote_prefix_ids.append(pid)
                result["prefixes_ensured"] += 1

        # 6. Comentarios y Payload del Túnel
        comments = self._build_comments(t_data, hub_key, profile_name)
        tunnel_payload = {
            "name": netbox_tunnel_name,
            "status": "active",
            "group": tg_id,
            "encapsulation": "ipsec-tunnel",
            "ipsec_profile": profile_id,
            "tenant": tenant_id,
            "description": f"VPN B2B con {tenant_name} en {hub_key}",
            "comments": comments,
            "tags": [tag_b2b_id, tag_vpn_id],
            "custom_fields": {
                "local_prefixes": local_prefix_ids,
                "remote_prefixes": remote_prefix_ids,
            },
        }

        # 7. Comprobar si el túnel ya existe
        res_t = self.client.get("vpn/tunnels", params={"name": netbox_tunnel_name})
        t_results = res_t.get("results", [])
        if t_results:
            tunnel_id = t_results[0]["id"]
            if not self.dry_run:
                self.client.patch("vpn/tunnels", tunnel_id, tunnel_payload)
            result["tunnel_updated"] = True
        else:
            if self.dry_run:
                logger.info(f"[DRY-RUN] Crear Tunnel: {netbox_tunnel_name} (Profile: {profile_name})")
                tunnel_id = None
                result["tunnel_created"] = True
            else:
                created_t = self.client.post("vpn/tunnels", tunnel_payload)
                tunnel_id = created_t["id"]
                result["tunnel_created"] = True

        # 8. Terminación del Túnel
        if self.dry_run:
            logger.info(f"[DRY-RUN] Crearía Termination para {netbox_tunnel_name} -> Interface {iface_id}")
            result["term_created"] = True
        else:
            res_term = self.client.get("vpn/tunnel-terminations", params={"tunnel_id": tunnel_id, "termination_id": iface_id})
            term_results = res_term.get("results", [])
            if not term_results:
                term_payload = {
                    "tunnel": tunnel_id,
                    "role": "peer",
                    "termination_type": "dcim.interface",
                    "termination_id": iface_id,
                }
                self.client.post("vpn/tunnel-terminations", term_payload)
                result["term_created"] = True

        return result
