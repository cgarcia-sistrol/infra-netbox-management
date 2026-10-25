"""Runner de conciliación e ingesta para túneles VPN de infraestructura en NetBox.

Modelado exclusivo de túneles no-B2B:
- Inter-Hub Transit (HUB00 <-> HUB02 simétrico)
- Cloud Transit Multi-Cloud (AWS y Azure)
- Hub-Spoke SD-WAN Overlays (HubVPN dialup)
- Acceso Remoto / Contingencia (VPNClient, VPNCExt, etc.)
Excluye estrictamente los túneles B2B con clientes/terceros.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from netbox_core.client import NetBoxClient

CATALOG_VPN_PATH = "/home/carlos/projects-ag/infra-netbox-management/inputs/firewall_vpn_tunnels_hub0_hub2.json"

# Mapeo de grupos de túneles en NetBox
TUNNEL_GROUPS = [
    {
        "name": "Inter-Hub Transit",
        "slug": "inter-hub-transit",
        "description": "Interconexión troncal punto a punto entre centros de datos (Hubs)",
    },
    {
        "name": "Cloud Transit (AWS / Azure)",
        "slug": "cloud-transit",
        "description": "Interconexiones troncales multi-cloud hacia AWS Direct Connect / VGW y Azure ExpressRoute / vNet GW",
    },
    {
        "name": "Hub-Spoke SD-WAN",
        "slug": "hub-spoke-sdwan",
        "description": "Concentradores y mallas overlay SD-WAN para sedes remotas y delegaciones",
    },
    {
        "name": "Remote Access / Dialup",
        "slug": "remote-access-dialup",
        "description": "Túneles dinámicos de contingencia y acceso administrativo",
    },
]

# Propuestas y perfiles criptográficos
CRYPTO_DEFINITIONS = {
    "ike_proposals": [
        {
            "name": "ike-prop-aes256-sha256-dh21",
            "encryption_algorithm": "aes-256-cbc",
            "authentication_algorithm": "hmac-sha256",
            "authentication_method": "preshared-keys",
            "group": 21,
            "description": "IKE Proposal AES-256-CBC SHA-256 DH21 (ECP 521)",
        },
        {
            "name": "ike-prop-aes256-sha256-dh20",
            "encryption_algorithm": "aes-256-cbc",
            "authentication_algorithm": "hmac-sha256",
            "authentication_method": "preshared-keys",
            "group": 20,
            "description": "IKE Proposal AES-256-CBC SHA-256 DH20 (ECP 384 - Azure)",
        },
        {
            "name": "ike-prop-aes128-sha1-dh2",
            "encryption_algorithm": "aes-128-cbc",
            "authentication_algorithm": "hmac-sha1",
            "authentication_method": "preshared-keys",
            "group": 2,
            "description": "IKE Proposal Legacy AES-128-CBC SHA-1 DH2 (AWS Hub02)",
        },
        {
            "name": "ike-prop-aes256-sha256-dh14",
            "encryption_algorithm": "aes-256-cbc",
            "authentication_algorithm": "hmac-sha256",
            "authentication_method": "preshared-keys",
            "group": 14,
            "description": "IKE Proposal AES-256-CBC SHA-256 DH14",
        },
    ],
    "ike_policies": [
        {
            "name": "ike-pol-v2-aes256-sha256-dh21",
            "version": 2,
            "mode": None,
            "proposal_name": "ike-prop-aes256-sha256-dh21",
            "description": "IKEv2 Policy AES-256 SHA-256 DH21 (Core & SD-WAN)",
        },
        {
            "name": "ike-pol-v2-azure-dh20",
            "version": 2,
            "mode": None,
            "proposal_name": "ike-prop-aes256-sha256-dh20",
            "description": "IKEv2 Policy Azure Transit DH20",
        },
        {
            "name": "ike-pol-v1-aws-legacy-dh2",
            "version": 1,
            "mode": "main",
            "proposal_name": "ike-prop-aes128-sha1-dh2",
            "description": "IKEv1 Policy AWS Legacy DH2",
        },
        {
            "name": "ike-pol-v2-spg-dh14",
            "version": 2,
            "mode": None,
            "proposal_name": "ike-prop-aes256-sha256-dh14",
            "description": "IKEv2 Policy SPG DH14",
        },
    ],
    "ipsec_proposals": [
        {
            "name": "ipsec-prop-aes256-sha256",
            "encryption_algorithm": "aes-256-cbc",
            "authentication_algorithm": "hmac-sha256",
            "description": "IPsec Phase 2 AES-256-CBC SHA-256",
        },
        {
            "name": "ipsec-prop-aes128-sha1",
            "encryption_algorithm": "aes-128-cbc",
            "authentication_algorithm": "hmac-sha1",
            "description": "IPsec Phase 2 Legacy AES-128-CBC SHA-1",
        },
    ],
    "ipsec_policies": [
        {
            "name": "ipsec-pol-aes256-sha256-pfs21",
            "proposal_name": "ipsec-prop-aes256-sha256",
            "pfs_group": 21,
            "description": "IPsec Policy AES-256 SHA-256 PFS Group 21",
        },
        {
            "name": "ipsec-pol-azure-pfs20",
            "proposal_name": "ipsec-prop-aes256-sha256",
            "pfs_group": 20,
            "description": "IPsec Policy Azure PFS Group 20",
        },
        {
            "name": "ipsec-pol-aws-legacy-pfs2",
            "proposal_name": "ipsec-prop-aes128-sha1",
            "pfs_group": 2,
            "description": "IPsec Policy AWS Legacy PFS Group 2",
        },
        {
            "name": "ipsec-pol-spg-pfs14",
            "proposal_name": "ipsec-prop-aes256-sha256",
            "pfs_group": 14,
            "description": "IPsec Policy SPG PFS Group 14",
        },
    ],
    "ipsec_profiles": [
        {
            "name": "ipsec-prof-interhub-dh21",
            "mode": "esp",
            "ike_policy_name": "ike-pol-v2-aes256-sha256-dh21",
            "ipsec_policy_name": "ipsec-pol-aes256-sha256-pfs21",
            "description": "Perfil IPsec Inter-Hub Core DH21",
        },
        {
            "name": "ipsec-prof-azure-dh20",
            "mode": "esp",
            "ike_policy_name": "ike-pol-v2-azure-dh20",
            "ipsec_policy_name": "ipsec-pol-azure-pfs20",
            "description": "Perfil IPsec Azure Transit DH20",
        },
        {
            "name": "ipsec-prof-aws-hub00-dh21",
            "mode": "esp",
            "ike_policy_name": "ike-pol-v2-aes256-sha256-dh21",
            "ipsec_policy_name": "ipsec-pol-aes256-sha256-pfs21",
            "description": "Perfil IPsec AWS HUB-00 DH21",
        },
        {
            "name": "ipsec-prof-aws-hub02-dh2",
            "mode": "esp",
            "ike_policy_name": "ike-pol-v1-aws-legacy-dh2",
            "ipsec_policy_name": "ipsec-pol-aws-legacy-pfs2",
            "description": "Perfil IPsec AWS HUB-02 Legacy DH2",
        },
        {
            "name": "ipsec-prof-sdwan-hub-dh21",
            "mode": "esp",
            "ike_policy_name": "ike-pol-v2-aes256-sha256-dh21",
            "ipsec_policy_name": "ipsec-pol-aes256-sha256-pfs21",
            "description": "Perfil IPsec Hub-Spoke SD-WAN DH21",
        },
        {
            "name": "ipsec-prof-spg-dh14",
            "mode": "esp",
            "ike_policy_name": "ike-pol-v2-spg-dh14",
            "ipsec_policy_name": "ipsec-pol-spg-pfs14",
            "description": "Perfil IPsec SPG Client DH14",
        },
    ],
}

# Tags de gobernanza
VPN_TAGS = [
    {"name": "vpn:inter-hub", "slug": "vpn-inter-hub", "color": "0284c7", "description": "Túnel troncal Inter-Hub"},
    {"name": "vpn:cloud-transit", "slug": "vpn-cloud-transit", "color": "2563eb", "description": "Túnel de tránsito Cloud (AWS/Azure)"},
    {"name": "vpn:sdwan-hub", "slug": "vpn-sdwan-hub", "color": "10b981", "description": "Concentrador SD-WAN Hub-Spoke"},
    {"name": "vpn:remote-access", "slug": "vpn-remote-access", "color": "64748b", "description": "Túnel de acceso remoto o contingencia"},
]

B2B_EXCLUSION_NAMES = {
    "to-Moeve", "to-Axpo", "to-PCA", "to-Orange", "to-LNC", "to-REEProxy",
    "to-Pascual-Gurb", "to-UVAX", "to-Pontedeume", "to-Meruelo", "to-Avila"
}


class VPNInfraIngestRunner:
    """Motor de ingesta de túneles no-B2B en NetBox."""

    def __init__(self, client: Optional[NetBoxClient] = None, dry_run: bool = True):
        self.nb = client or NetBoxClient()
        self.dry_run = dry_run
        self.catalog = self._load_catalog()

        # Cache de IDs en NetBox
        self.tag_ids: Dict[str, int] = {}
        self.group_ids: Dict[str, int] = {}
        self.ike_prop_ids: Dict[str, int] = {}
        self.ike_pol_ids: Dict[str, int] = {}
        self.ipsec_prop_ids: Dict[str, int] = {}
        self.ipsec_pol_ids: Dict[str, int] = {}
        self.ipsec_prof_ids: Dict[str, int] = {}
        self.device_ifaces: Dict[int, Dict[str, int]] = {}

        self.stats = {
            "groups_created": 0,
            "crypto_created": 0,
            "tunnels_created": 0,
            "tunnels_updated": 0,
            "terminations_created": 0,
            "ips_associated": 0,
            "skipped_b2b": 0,
            "errors": [],
        }

    def _load_catalog(self) -> Dict[str, Any]:
        if not os.path.exists(CATALOG_VPN_PATH):
            raise FileNotFoundError(f"Catálogo VPN no encontrado en {CATALOG_VPN_PATH}")
        with open(CATALOG_VPN_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def run(self) -> Dict[str, Any]:
        mode_str = "DRY-RUN" if self.dry_run else "COMMIT"
        print(f"=== Iniciando Ingesta de Túneles VPN de Infraestructura [Modo: {mode_str}] ===")

        self.reconcile_tags()
        self.reconcile_tunnel_groups()
        self.reconcile_crypto_stack()
        self.cache_device_interfaces()

        self.ingest_inter_hub_tunnel()
        self.ingest_cloud_transit_tunnels()
        self.ingest_sdwan_hub_tunnels()
        self.ingest_remote_access_tunnels()

        print(f"\n=== Resumen de Ingesta VPN [{mode_str}] ===")
        print(f"  Grupos gestionados: {self.stats['groups_created']}")
        print(f"  Perfiles criptográficos gestionados: {self.stats['crypto_created']}")
        print(f"  Túneles creados: {self.stats['tunnels_created']}")
        print(f"  Túneles actualizados: {self.stats['tunnels_updated']}")
        print(f"  Terminaciones vinculadas: {self.stats['terminations_created']}")
        print(f"  IPs asociadas/creadas: {self.stats['ips_associated']}")
        print(f"  Túneles B2B excluidos (para fase 2): {self.stats['skipped_b2b']}")
        if self.stats["errors"]:
            print(f"  Errores: {len(self.stats['errors'])}")
            for err in self.stats["errors"]:
                print(f"    - {err}")

        return self.stats

    def reconcile_tags(self):
        print("[*] Reconciliando tags de gobernanza VPN...")
        existing = {t["slug"]: t["id"] for t in self.nb.get_all("extras/tags")}
        for tag in VPN_TAGS:
            slug = tag["slug"]
            if slug in existing:
                self.tag_ids[slug] = existing[slug]
            else:
                if self.dry_run:
                    print(f"  [DRY-RUN] Crearía tag {tag['name']}")
                    self.tag_ids[slug] = 9999
                else:
                    res = self.nb.post("extras/tags", tag)
                    self.tag_ids[slug] = res["id"]
                    print(f"  [OK] Tag creado: {tag['name']}")

    def reconcile_tunnel_groups(self):
        print("[*] Reconciliando grupos de túneles...")
        existing = {g["slug"]: g["id"] for g in self.nb.get_all("vpn/tunnel-groups")}
        for grp in TUNNEL_GROUPS:
            slug = grp["slug"]
            if slug in existing:
                self.group_ids[slug] = existing[slug]
            else:
                if self.dry_run:
                    print(f"  [DRY-RUN] Crearía grupo {grp['name']}")
                    self.group_ids[slug] = 9999
                    self.stats["groups_created"] += 1
                else:
                    res = self.nb.post("vpn/tunnel-groups", grp)
                    self.group_ids[slug] = res["id"]
                    self.stats["groups_created"] += 1
                    print(f"  [OK] Grupo creado: {grp['name']}")

    def reconcile_crypto_stack(self):
        print("[*] Reconciliando stack criptográfico (IKE e IPsec)...")
        # 1. IKE Proposals
        existing_ike_props = {p["name"]: p["id"] for p in self.nb.get_all("vpn/ike-proposals")}
        for p in CRYPTO_DEFINITIONS["ike_proposals"]:
            name = p["name"]
            if name in existing_ike_props:
                self.ike_prop_ids[name] = existing_ike_props[name]
            else:
                if self.dry_run:
                    print(f"  [DRY-RUN] Crearía IKE Proposal {name}")
                    self.ike_prop_ids[name] = 9991
                    self.stats["crypto_created"] += 1
                else:
                    res = self.nb.post("vpn/ike-proposals", p)
                    self.ike_prop_ids[name] = res["id"]
                    self.stats["crypto_created"] += 1

        # 2. IKE Policies
        existing_ike_pols = {p["name"]: p["id"] for p in self.nb.get_all("vpn/ike-policies")}
        for p in CRYPTO_DEFINITIONS["ike_policies"]:
            name = p["name"]
            prop_id = self.ike_prop_ids.get(p["proposal_name"])
            payload = {
                "name": p["name"],
                "version": p["version"],
                "description": p["description"],
                "proposals": [prop_id] if prop_id else [],
            }
            if p.get("mode"):
                payload["mode"] = p["mode"]
            if name in existing_ike_pols:
                self.ike_pol_ids[name] = existing_ike_pols[name]
            else:
                if self.dry_run:
                    print(f"  [DRY-RUN] Crearía IKE Policy {name}")
                    self.ike_pol_ids[name] = 9992
                    self.stats["crypto_created"] += 1
                else:
                    res = self.nb.post("vpn/ike-policies", payload)
                    self.ike_pol_ids[name] = res["id"]
                    self.stats["crypto_created"] += 1

        # 3. IPsec Proposals
        existing_ipsec_props = {p["name"]: p["id"] for p in self.nb.get_all("vpn/ipsec-proposals")}
        for p in CRYPTO_DEFINITIONS["ipsec_proposals"]:
            name = p["name"]
            if name in existing_ipsec_props:
                self.ipsec_prop_ids[name] = existing_ipsec_props[name]
            else:
                if self.dry_run:
                    print(f"  [DRY-RUN] Crearía IPsec Proposal {name}")
                    self.ipsec_prop_ids[name] = 9993
                    self.stats["crypto_created"] += 1
                else:
                    res = self.nb.post("vpn/ipsec-proposals", p)
                    self.ipsec_prop_ids[name] = res["id"]
                    self.stats["crypto_created"] += 1

        # 4. IPsec Policies
        existing_ipsec_pols = {p["name"]: p["id"] for p in self.nb.get_all("vpn/ipsec-policies")}
        for p in CRYPTO_DEFINITIONS["ipsec_policies"]:
            name = p["name"]
            prop_id = self.ipsec_prop_ids.get(p["proposal_name"])
            payload = {
                "name": p["name"],
                "pfs_group": p["pfs_group"],
                "description": p["description"],
                "proposals": [prop_id] if prop_id else [],
            }
            if name in existing_ipsec_pols:
                self.ipsec_pol_ids[name] = existing_ipsec_pols[name]
            else:
                if self.dry_run:
                    print(f"  [DRY-RUN] Crearía IPsec Policy {name}")
                    self.ipsec_pol_ids[name] = 9994
                    self.stats["crypto_created"] += 1
                else:
                    res = self.nb.post("vpn/ipsec-policies", payload)
                    self.ipsec_pol_ids[name] = res["id"]
                    self.stats["crypto_created"] += 1

        # 5. IPsec Profiles
        existing_ipsec_profs = {p["name"]: p["id"] for p in self.nb.get_all("vpn/ipsec-profiles")}
        for p in CRYPTO_DEFINITIONS["ipsec_profiles"]:
            name = p["name"]
            ike_pol_id = self.ike_pol_ids.get(p["ike_policy_name"])
            ipsec_pol_id = self.ipsec_pol_ids.get(p["ipsec_policy_name"])
            payload = {
                "name": p["name"],
                "mode": p["mode"],
                "ike_policy": ike_pol_id,
                "ipsec_policy": ipsec_pol_id,
                "description": p["description"],
            }
            if name in existing_ipsec_profs:
                self.ipsec_prof_ids[name] = existing_ipsec_profs[name]
            else:
                if self.dry_run:
                    print(f"  [DRY-RUN] Crearía IPsec Profile {name}")
                    self.ipsec_prof_ids[name] = 9995
                    self.stats["crypto_created"] += 1
                else:
                    res = self.nb.post("vpn/ipsec-profiles", payload)
                    self.ipsec_prof_ids[name] = res["id"]
                    self.stats["crypto_created"] += 1

    def cache_device_interfaces(self):
        print("[*] Cacheando interfaces de cortafuegos ID: 8 (HUB-00) y ID: 2 (HUB-02)...")
        for dev_id in [8, 2]:
            ifaces = self.nb.get_all("dcim/interfaces", params={"device_id": dev_id})
            self.device_ifaces[dev_id] = {i["name"]: i["id"] for i in ifaces}
            print(f"  Device {dev_id}: {len(self.device_ifaces[dev_id])} interfaces cacheadas.")

    def _ensure_ip_assigned(self, ip_str: str, interface_id: int, description: str):
        """Asegura que la IP esté creada y asignada a la interfaz del firewall."""
        if not ip_str or not interface_id or interface_id > 9000:
            return

        ip_clean = ip_str.split()[0]
        # Formatear CIDR a /32 o /30
        if " " in ip_str:
            ip_val, mask = ip_str.split()[:2]
            if mask == "255.255.255.255":
                cidr = f"{ip_val}/32"
            elif mask == "255.255.255.252":
                cidr = f"{ip_val}/30"
            else:
                cidr = f"{ip_val}/32"
        elif "/" in ip_str:
            cidr = ip_str
        else:
            cidr = f"{ip_str}/32"

        raw_ip = ip_clean.split("/")[0]
        existing = self.nb.get("ipam/ip-addresses", params={"q": raw_ip})
        results = [r for r in existing.get("results", []) if r["address"].split("/")[0] == raw_ip]
        if results:
            ip_obj = results[0]
            if ip_obj.get("assigned_object_id") != interface_id:
                if self.dry_run:
                    print(f"    [DRY-RUN] Asociaría IP {ip_obj['address']} a interfaz ID {interface_id}")
                    self.stats["ips_associated"] += 1
                else:
                    self.nb.patch("ipam/ip-addresses", ip_obj["id"], {
                        "assigned_object_type": "dcim.interface",
                        "assigned_object_id": interface_id,
                        "description": description[:200]
                    })
                    print(f"    [OK] IP {ip_obj['address']} asociada a interfaz ID {interface_id}")
                    self.stats["ips_associated"] += 1
        else:
            if self.dry_run:
                print(f"    [DRY-RUN] Crearía y asociaría nueva IP {cidr} a interfaz ID {interface_id}")
                self.stats["ips_associated"] += 1
            else:
                self.nb.post("ipam/ip-addresses", {
                    "address": cidr,
                    "status": "active",
                    "assigned_object_type": "dcim.interface",
                    "assigned_object_id": interface_id,
                    "description": description[:200]
                })
                print(f"    [OK] IP {cidr} creada y asignada a interfaz ID {interface_id}")
                self.stats["ips_associated"] += 1

    def _create_or_update_tunnel(
        self,
        name: str,
        group_slug: str,
        profile_name: str,
        description: str,
        comments: str,
        tag_slug: str,
    ) -> Optional[int]:
        group_id = self.group_ids.get(group_slug)
        profile_id = self.ipsec_prof_ids.get(profile_name)
        tag_id = self.tag_ids.get(tag_slug)

        payload = {
            "name": name,
            "status": "active",
            "encapsulation": "ipsec-tunnel",
            "group": group_id,
            "ipsec_profile": profile_id,
            "description": description[:200],
            "comments": comments,
            "tags": [tag_id] if tag_id else [],
        }

        existing = self.nb.get("vpn/tunnels", params={"name": name})
        results = existing.get("results", [])
        if results:
            tun_id = results[0]["id"]
            if self.dry_run:
                print(f"  [DRY-RUN] Actualizaría túnel existente '{name}' (ID: {tun_id})")
                self.stats["tunnels_updated"] += 1
            else:
                self.nb.patch("vpn/tunnels", tun_id, payload)
                print(f"  [OK] Túnel '{name}' actualizado.")
                self.stats["tunnels_updated"] += 1
            return tun_id
        else:
            if self.dry_run:
                print(f"  [DRY-RUN] Crearía nuevo túnel '{name}' en grupo '{group_slug}'")
                self.stats["tunnels_created"] += 1
                return 9990
            else:
                res = self.nb.post("vpn/tunnels", payload)
                tun_id = res["id"]
                print(f"  [OK] Túnel '{name}' creado con ID {tun_id}.")
                self.stats["tunnels_created"] += 1
                return tun_id

    def _ensure_termination(self, tunnel_id: int, role: str, iface_id: int):
        if self.dry_run or not tunnel_id or tunnel_id > 9000 or not iface_id or iface_id > 9000:
            if self.dry_run:
                print(f"    [DRY-RUN] Crearía terminación role='{role}' vinculada a interfaz ID {iface_id}")
                self.stats["terminations_created"] += 1
            return

        # Comprobar si ya existe terminación para ese túnel e interfaz
        existing = self.nb.get("vpn/tunnel-terminations", params={"tunnel_id": tunnel_id, "termination_id": iface_id})
        if existing.get("results"):
            return

        payload = {
            "tunnel": tunnel_id,
            "role": role,
            "termination_type": "dcim.interface",
            "termination_id": iface_id,
        }
        try:
            self.nb.post("vpn/tunnel-terminations", payload)
            print(f"    [OK] Terminación role='{role}' vinculada a interfaz ID {iface_id}")
            self.stats["terminations_created"] += 1
        except Exception as e:
            print(f"    [WARN] Fallo creando terminación: {e}")

    # =========================================================================
    # 1. Inter-Hub Transit (HUB-00 <-> HUB-02)
    # =========================================================================
    def ingest_inter_hub_tunnel(self):
        print("\n--- [1/4] Ingestando Túnel Troncal Inter-Hub (Simétrico) ---")
        tun_name = "Inter-Hub-HUB00-HUB02"
        desc = "Troncal directo IPsec entre Madrid CPD (HUB-00) y JESP (HUB-02)"
        comments = (
            "## Inter-Hub Transit Link\n"
            "- **Extremo A**: HUB-00 (`FortiGate-100F`) - Interfaz `to-Hub02` (IP: `10.254.13.1/32`)\n"
            "- **Extremo B**: HUB-02 (`FGT100-JES`) - Interfaz `to-Hub00` (IP: `10.254.13.2/32`)\n"
            "- **WAN Underlay**: `212.81.134.189` <-> `212.81.163.114` (wan1)\n"
            "- **Criptografía**: IKEv2, AES-256-SHA256, DH Group 21 (PFS 21)\n"
            "- **Enrutamiento**: Tránsito inter-hub, sesiones BGP y contingencia de tráfico interno."
        )

        tun_id = self._create_or_update_tunnel(
            name=tun_name,
            group_slug="inter-hub-transit",
            profile_name="ipsec-prof-interhub-dh21",
            description=desc,
            comments=comments,
            tag_slug="vpn-inter-hub",
        )

        iface_hub0 = self.device_ifaces.get(8, {}).get("to-Hub02")
        iface_hub2 = self.device_ifaces.get(2, {}).get("to-Hub00")

        if iface_hub0:
            self._ensure_termination(tun_id, role="peer", iface_id=iface_hub0)
            self._ensure_ip_assigned("10.254.13.1/32", iface_hub0, "Inter-Hub Transit IP (HUB-00)")
        if iface_hub2:
            self._ensure_termination(tun_id, role="peer", iface_id=iface_hub2)
            self._ensure_ip_assigned("10.254.13.2/32", iface_hub2, "Inter-Hub Transit IP (HUB-02)")

    # =========================================================================
    # 2. Cloud Transit (AWS / Azure)
    # =========================================================================
    def ingest_cloud_transit_tunnels(self):
        print("\n--- [2/4] Ingestando Túneles Cloud Transit (AWS / Azure) ---")

        cloud_configs = [
            # HUB-00 Azure
            {
                "dev_id": 8,
                "name": "HUB00-to-Azure-01",
                "iface": "to-Azure-01",
                "peer_gw": "20.73.227.202",
                "local_ip": "169.254.21.148/32",
                "remote_ip": "169.254.21.1",
                "wan": "wan1",
                "profile": "ipsec-prof-azure-dh20",
                "desc": "HUB-00 a Azure Express/vNet Gateway Primario",
            },
            {
                "dev_id": 8,
                "name": "HUB00-to-Azure-02",
                "iface": "to-Azure-02",
                "peer_gw": "20.73.227.208",
                "local_ip": "169.254.22.148/32",
                "remote_ip": "169.254.22.1",
                "wan": "wan2",
                "profile": "ipsec-prof-azure-dh20",
                "desc": "HUB-00 a Azure Express/vNet Gateway Secundario",
            },
            # HUB-02 Azure
            {
                "dev_id": 2,
                "name": "HUB02-to-Azure-01",
                "iface": "to-Azure-01",
                "peer_gw": "20.73.227.202",
                "local_ip": "169.254.21.152/32",
                "remote_ip": "169.254.21.1",
                "wan": "wan1",
                "profile": "ipsec-prof-azure-dh20",
                "desc": "HUB-02 a Azure Express/vNet Gateway Primario",
            },
            {
                "dev_id": 2,
                "name": "HUB02-to-Azure-02",
                "iface": "to-Azure-02",
                "peer_gw": "20.73.227.208",
                "local_ip": "169.254.22.152/32",
                "remote_ip": "169.254.22.1",
                "wan": "wan2",
                "profile": "ipsec-prof-azure-dh20",
                "desc": "HUB-02 a Azure Express/vNet Gateway Secundario",
            },
            # HUB-00 AWS
            {
                "dev_id": 8,
                "name": "HUB00-to-Aws-01",
                "iface": "to-Aws-01",
                "peer_gw": "34.247.199.6",
                "local_ip": "169.254.239.6/30",
                "remote_ip": "169.254.239.5",
                "wan": "wan1",
                "profile": "ipsec-prof-aws-hub00-dh21",
                "desc": "HUB-00 a AWS TGW / VGW Túnel 1",
            },
            {
                "dev_id": 8,
                "name": "HUB00-to-Aws-02",
                "iface": "to-Aws-02",
                "peer_gw": "52.215.210.228",
                "local_ip": "169.254.76.34/30",
                "remote_ip": "169.254.76.33",
                "wan": "wan1",
                "profile": "ipsec-prof-aws-hub00-dh21",
                "desc": "HUB-00 a AWS TGW / VGW Túnel 2",
            },
            # HUB-02 AWS
            {
                "dev_id": 2,
                "name": "HUB02-to-Aws-01",
                "iface": "to-Aws-01",
                "peer_gw": "52.49.246.125",
                "local_ip": "169.254.39.118/30",
                "remote_ip": "169.254.39.117",
                "wan": "wan1",
                "profile": "ipsec-prof-aws-hub02-dh2",
                "desc": "HUB-02 a AWS TGW / VGW Túnel 1 (Legacy DH2)",
            },
            {
                "dev_id": 2,
                "name": "HUB02-to-Aws-02",
                "iface": "to-Aws-02",
                "peer_gw": "52.208.121.86",
                "local_ip": "169.254.24.54/30",
                "remote_ip": "169.254.24.53",
                "wan": "wan2",
                "profile": "ipsec-prof-aws-hub02-dh2",
                "desc": "HUB-02 a AWS TGW / VGW Túnel 2 (Legacy DH2)",
            },
        ]

        for c in cloud_configs:
            comments = (
                f"## Cloud Transit: {c['name']}\n"
                f"- **Firewall**: Device ID {c['dev_id']} (`{c['iface']}`)\n"
                f"- **Peer Gateway Remoto**: `{c['peer_gw']}`\n"
                f"- **WAN Salida**: `{c['wan']}`\n"
                f"- **IP Tránsito Local**: `{c['local_ip']}`\n"
                f"- **IP Tránsito Cloud**: `{c['remote_ip']}`\n"
                f"- **BGP Neighbor**: Peering BGP over IPsec para propagación de VPCs/vNets."
            )
            tun_id = self._create_or_update_tunnel(
                name=c["name"],
                group_slug="cloud-transit",
                profile_name=c["profile"],
                description=c["desc"],
                comments=comments,
                tag_slug="vpn-cloud-transit",
            )
            iface_id = self.device_ifaces.get(c["dev_id"], {}).get(c["iface"])
            if iface_id:
                self._ensure_termination(tun_id, role="peer", iface_id=iface_id)
                self._ensure_ip_assigned(c["local_ip"], iface_id, f"Cloud Transit IP {c['name']}")

    # =========================================================================
    # 3. Hub-Spoke SD-WAN Overlays
    # =========================================================================
    def ingest_sdwan_hub_tunnels(self):
        print("\n--- [3/4] Ingestando Concentradores SD-WAN Hub-Spoke ---")

        sdwan_configs = [
            {
                "dev_id": 8,
                "name": "HUB00-HubVPN",
                "iface": "HubVPN",
                "ip": "10.254.10.1/32",
                "net": "10.254.10.0/24",
                "desc": "Concentrador Dialup SD-WAN Hub-Spoke en Madrid CPD (HUB-00)",
            },
            {
                "dev_id": 2,
                "name": "HUB02-HubVPN",
                "iface": "HubVPN",
                "ip": "10.254.11.1/32",
                "net": "10.254.11.0/24",
                "desc": "Concentrador Dialup SD-WAN Hub-Spoke en JESP (HUB-02)",
            },
        ]

        for s in sdwan_configs:
            comments = (
                f"## SD-WAN Overlay Dialup Hub: {s['name']}\n"
                f"- **Firewall**: Device ID {s['dev_id']}\n"
                f"- **Tipo**: Concentrador Dialup multipunto (`0.0.0.0`)\n"
                f"- **IP Local Hub**: `{s['ip']}`\n"
                f"- **Subred Overlay Spokes**: `{s['net']}`\n"
                f"- **Perfil Criptográfico**: IKEv2 AES-256-SHA256 DH21 (PFS 21)\n"
                f"- **Función**: Malla SD-WAN para interconexión de todas las sedes y delegaciones remotas."
            )
            tun_id = self._create_or_update_tunnel(
                name=s["name"],
                group_slug="hub-spoke-sdwan",
                profile_name="ipsec-prof-sdwan-hub-dh21",
                description=s["desc"],
                comments=comments,
                tag_slug="vpn-sdwan-hub",
            )
            iface_id = self.device_ifaces.get(s["dev_id"], {}).get(s["iface"])
            if iface_id:
                self._ensure_termination(tun_id, role="hub", iface_id=iface_id)
                self._ensure_ip_assigned(s["ip"], iface_id, f"SD-WAN Hub Gateway IP ({s['name']})")

    # =========================================================================
    # 4. Remote Access / Dialup Contingency
    # =========================================================================
    def ingest_remote_access_tunnels(self):
        print("\n--- [4/4] Ingestando Túneles de Acceso Remoto / Contingencia ---")

        remote_configs = [
            # HUB-00
            {"dev_id": 8, "name": "HUB00-To_Client_SPG", "iface": "To_Client_SPG", "peer": "195.76.33.168", "prof": "ipsec-prof-spg-dh14", "desc": "Acceso Remoto SPG (HUB-00)"},
            {"dev_id": 8, "name": "HUB00-VPNClient", "iface": "VPNClient", "peer": "0.0.0.0 (Dialup)", "prof": "ipsec-prof-interhub-dh21", "desc": "Acceso Remoto VPN Client (HUB-00)"},
            {"dev_id": 8, "name": "HUB00-VPNCExt", "iface": "VPNCExt", "peer": "0.0.0.0 (Dialup)", "prof": "ipsec-prof-interhub-dh21", "desc": "Acceso Remoto Extranet Dialup (HUB-00)"},
            # HUB-02
            {"dev_id": 2, "name": "HUB02-To_Client_SPG", "iface": "To_Client_SPG", "peer": "195.76.33.168", "prof": "ipsec-prof-spg-dh14", "desc": "Acceso Remoto SPG (HUB-02)"},
            {"dev_id": 2, "name": "HUB02-VPNClient", "iface": "VPNClient", "peer": "0.0.0.0 (Dialup)", "prof": "ipsec-prof-interhub-dh21", "desc": "Acceso Remoto VPN Client (HUB-02)"},
            {"dev_id": 2, "name": "HUB02-VPNCExt", "iface": "VPNCExt", "peer": "0.0.0.0 (Dialup)", "prof": "ipsec-prof-interhub-dh21", "desc": "Acceso Remoto Extranet Dialup (HUB-02)"},
            {"dev_id": 2, "name": "HUB02-VPNClient_LDAP", "iface": "VPNClient_LDAP", "peer": "0.0.0.0 (Dialup)", "prof": "ipsec-prof-interhub-dh21", "desc": "Acceso Remoto LDAP (HUB-02)"},
        ]

        # Contabilizar B2B excluidos para reporte
        for alias in ["HUB-00", "HUB-02"]:
            for tun in self.catalog.get(alias, {}).get("tunnels", []):
                if tun.get("tunnel_name") in B2B_EXCLUSION_NAMES:
                    self.stats["skipped_b2b"] += 1

        for r in remote_configs:
            comments = (
                f"## Remote Access: {r['name']}\n"
                f"- **Firewall**: Device ID {r['dev_id']} (`{r['iface']}`)\n"
                f"- **Peer / Dialup**: `{r['peer']}`\n"
                f"- **Propósito**: Conectividad contingente o clientes dedicados."
            )
            tun_id = self._create_or_update_tunnel(
                name=r["name"],
                group_slug="remote-access-dialup",
                profile_name=r["prof"],
                description=r["desc"],
                comments=comments,
                tag_slug="vpn-remote-access",
            )
            iface_id = self.device_ifaces.get(r["dev_id"], {}).get(r["iface"])
            if iface_id:
                self._ensure_termination(tun_id, role="hub" if "0.0.0.0" in r["peer"] else "peer", iface_id=iface_id)
