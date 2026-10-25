"""Runner de reconciliación y creación exclusiva de perfiles criptográficos B2B en NetBox."""

from typing import Any, Dict, List, Optional
from netbox_core.client import NetBoxClient

B2B_CRYPTO_DEFINITIONS = {
    "ike_proposals": [
        {
            "name": "ike-prop-aes256-sha256-dh14",
            "encryption_algorithm": "aes-256-cbc",
            "authentication_algorithm": "hmac-sha256",
            "authentication_method": "preshared-keys",
            "group": 14,
            "description": "IKE Proposal AES-256-CBC SHA-256 DH14 (B2B Standard)",
        },
        {
            "name": "ike-prop-aes256-sha512-dh19",
            "encryption_algorithm": "aes-256-cbc",
            "authentication_algorithm": "hmac-sha512",
            "authentication_method": "preshared-keys",
            "group": 19,
            "description": "IKE Proposal AES-256-CBC SHA-512 DH19 (NIST P-256 - Axpo)",
        },
        {
            "name": "ike-prop-aes256-sha512-dh2",
            "encryption_algorithm": "aes-256-cbc",
            "authentication_algorithm": "hmac-sha512",
            "authentication_method": "preshared-keys",
            "group": 2,
            "description": "IKE Proposal Legacy AES-256-CBC SHA-512 DH2 (Pascual-Gurb)",
        },
    ],
    "ike_policies": [
        {
            "name": "ike-pol-v2-b2b-standard-dh14",
            "version": 2,
            "mode": None,
            "proposal_name": "ike-prop-aes256-sha256-dh14",
            "description": "IKEv2 Policy B2B Standard DH14",
        },
        {
            "name": "ike-pol-v2-b2b-axpo-dh19",
            "version": 2,
            "mode": None,
            "proposal_name": "ike-prop-aes256-sha512-dh19",
            "description": "IKEv2 Policy Axpo Custom DH19",
        },
        {
            "name": "ike-pol-v2-b2b-legacy-dh2",
            "version": 2,
            "mode": None,
            "proposal_name": "ike-prop-aes256-sha512-dh2",
            "description": "IKEv2 Policy Legacy DH2 (Pascual-Gurb)",
        },
    ],
    "ipsec_proposals": [
        {
            "name": "ipsec-prop-aes256-sha256",
            "encryption_algorithm": "aes-256-cbc",
            "authentication_algorithm": "hmac-sha256",
            "description": "IPsec Phase 2 AES-256-CBC SHA-256 (B2B Standard)",
        },
        {
            "name": "ipsec-prop-aes256-sha512",
            "encryption_algorithm": "aes-256-cbc",
            "authentication_algorithm": "hmac-sha512",
            "description": "IPsec Phase 2 AES-256-CBC SHA-512 (Axpo / Pascual)",
        },
    ],
    "ipsec_policies": [
        {
            "name": "ipsec-pol-b2b-standard-pfs14",
            "proposal_name": "ipsec-prop-aes256-sha256",
            "pfs_group": 14,
            "description": "IPsec Policy B2B Standard PFS Group 14",
        },
        {
            "name": "ipsec-pol-b2b-axpo-pfs19",
            "proposal_name": "ipsec-prop-aes256-sha512",
            "pfs_group": 19,
            "description": "IPsec Policy Axpo PFS Group 19",
        },
        {
            "name": "ipsec-pol-b2b-legacy-pfs2",
            "proposal_name": "ipsec-prop-aes256-sha512",
            "pfs_group": 2,
            "description": "IPsec Policy Legacy PFS Group 2",
        },
    ],
    "ipsec_profiles": [
        {
            "name": "ipsec-prof-b2b-standard-dh14",
            "mode": "esp",
            "ike_policy_name": "ike-pol-v2-b2b-standard-dh14",
            "ipsec_policy_name": "ipsec-pol-b2b-standard-pfs14",
            "description": "Perfil IPsec B2B Estándar Corporativo (AES256-SHA256 DH14)",
        },
        {
            "name": "ipsec-prof-b2b-axpo-dh19",
            "mode": "esp",
            "ike_policy_name": "ike-pol-v2-b2b-axpo-dh19",
            "ipsec_policy_name": "ipsec-pol-b2b-axpo-pfs19",
            "description": "Perfil IPsec B2B Axpo Custom (AES256-SHA512 DH19)",
        },
        {
            "name": "ipsec-prof-b2b-legacy-dh2",
            "mode": "esp",
            "ike_policy_name": "ike-pol-v2-b2b-legacy-dh2",
            "ipsec_policy_name": "ipsec-pol-b2b-legacy-pfs2",
            "description": "Perfil IPsec B2B Legacy Retrocompatibilidad (AES256-SHA512 DH2)",
        },
    ],
}


class B2BCryptoIngestRunner:
    """Motor de ingesta de perfiles criptográficos B2B."""

    def __init__(self, client: Optional[NetBoxClient] = None, dry_run: bool = True):
        self.nb = client or NetBoxClient()
        self.dry_run = dry_run

        self.ike_prop_ids: Dict[str, int] = {}
        self.ike_pol_ids: Dict[str, int] = {}
        self.ipsec_prop_ids: Dict[str, int] = {}
        self.ipsec_pol_ids: Dict[str, int] = {}
        self.ipsec_prof_ids: Dict[str, int] = {}

        self.stats = {
            "proposals_created": 0,
            "proposals_reused": 0,
            "policies_created": 0,
            "policies_reused": 0,
            "profiles_created": 0,
            "profiles_reused": 0,
            "errors": [],
        }

    def run(self) -> Dict[str, Any]:
        mode_str = "DRY-RUN" if self.dry_run else "COMMIT"
        print(f"=== Iniciando Ingesta de Perfiles Criptográficos B2B [Modo: {mode_str}] ===")

        self.reconcile_ike_proposals()
        self.reconcile_ike_policies()
        self.reconcile_ipsec_proposals()
        self.reconcile_ipsec_policies()
        self.reconcile_ipsec_profiles()

        print(f"\n=== Resumen de Ingesta Criptográfica B2B [{mode_str}] ===")
        print(f"  IKE Proposals: {self.stats['proposals_created']} creadas, {self.stats['proposals_reused']} reutilizadas")
        print(f"  IKE/IPsec Policies: {self.stats['policies_created']} creadas, {self.stats['policies_reused']} reutilizadas")
        print(f"  IPsec Profiles: {self.stats['profiles_created']} creados, {self.stats['profiles_reused']} reutilizados")
        if self.stats["errors"]:
            print(f"  Errores: {len(self.stats['errors'])}")
            for err in self.stats["errors"]:
                print(f"    - {err}")

        return self.stats

    def reconcile_ike_proposals(self):
        print("[*] Reconciliando IKE Proposals...")
        existing = {p["name"]: p["id"] for p in self.nb.get_all("vpn/ike-proposals")}
        for p in B2B_CRYPTO_DEFINITIONS["ike_proposals"]:
            name = p["name"]
            if name in existing:
                self.ike_prop_ids[name] = existing[name]
                self.stats["proposals_reused"] += 1
                print(f"  [EXISTE] IKE Proposal '{name}' (ID: {existing[name]})")
            else:
                if self.dry_run:
                    print(f"  [DRY-RUN] Crearía IKE Proposal '{name}'")
                    self.ike_prop_ids[name] = 8881
                    self.stats["proposals_created"] += 1
                else:
                    res = self.nb.post("vpn/ike-proposals", p)
                    self.ike_prop_ids[name] = res["id"]
                    self.stats["proposals_created"] += 1
                    print(f"  [OK] IKE Proposal creada: '{name}' (ID: {res['id']})")

    def reconcile_ike_policies(self):
        print("[*] Reconciliando IKE Policies...")
        existing = {p["name"]: p["id"] for p in self.nb.get_all("vpn/ike-policies")}
        for p in B2B_CRYPTO_DEFINITIONS["ike_policies"]:
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

            if name in existing:
                self.ike_pol_ids[name] = existing[name]
                self.stats["policies_reused"] += 1
                print(f"  [EXISTE] IKE Policy '{name}' (ID: {existing[name]})")
            else:
                if self.dry_run:
                    print(f"  [DRY-RUN] Crearía IKE Policy '{name}'")
                    self.ike_pol_ids[name] = 8882
                    self.stats["policies_created"] += 1
                else:
                    res = self.nb.post("vpn/ike-policies", payload)
                    self.ike_pol_ids[name] = res["id"]
                    self.stats["policies_created"] += 1
                    print(f"  [OK] IKE Policy creada: '{name}' (ID: {res['id']})")

    def reconcile_ipsec_proposals(self):
        print("[*] Reconciliando IPsec Proposals...")
        existing = {p["name"]: p["id"] for p in self.nb.get_all("vpn/ipsec-proposals")}
        for p in B2B_CRYPTO_DEFINITIONS["ipsec_proposals"]:
            name = p["name"]
            if name in existing:
                self.ipsec_prop_ids[name] = existing[name]
                self.stats["proposals_reused"] += 1
                print(f"  [EXISTE] IPsec Proposal '{name}' (ID: {existing[name]})")
            else:
                if self.dry_run:
                    print(f"  [DRY-RUN] Crearía IPsec Proposal '{name}'")
                    self.ipsec_prop_ids[name] = 8883
                    self.stats["proposals_created"] += 1
                else:
                    res = self.nb.post("vpn/ipsec-proposals", p)
                    self.ipsec_prop_ids[name] = res["id"]
                    self.stats["proposals_created"] += 1
                    print(f"  [OK] IPsec Proposal creada: '{name}' (ID: {res['id']})")

    def reconcile_ipsec_policies(self):
        print("[*] Reconciliando IPsec Policies...")
        existing = {p["name"]: p["id"] for p in self.nb.get_all("vpn/ipsec-policies")}
        for p in B2B_CRYPTO_DEFINITIONS["ipsec_policies"]:
            name = p["name"]
            prop_id = self.ipsec_prop_ids.get(p["proposal_name"])
            payload = {
                "name": p["name"],
                "pfs_group": p["pfs_group"],
                "description": p["description"],
                "proposals": [prop_id] if prop_id else [],
            }
            if name in existing:
                self.ipsec_pol_ids[name] = existing[name]
                self.stats["policies_reused"] += 1
                print(f"  [EXISTE] IPsec Policy '{name}' (ID: {existing[name]})")
            else:
                if self.dry_run:
                    print(f"  [DRY-RUN] Crearía IPsec Policy '{name}'")
                    self.ipsec_pol_ids[name] = 8884
                    self.stats["policies_created"] += 1
                else:
                    res = self.nb.post("vpn/ipsec-policies", payload)
                    self.ipsec_pol_ids[name] = res["id"]
                    self.stats["policies_created"] += 1
                    print(f"  [OK] IPsec Policy creada: '{name}' (ID: {res['id']})")

    def reconcile_ipsec_profiles(self):
        print("[*] Reconciliando IPsec Profiles...")
        existing = {p["name"]: p["id"] for p in self.nb.get_all("vpn/ipsec-profiles")}
        for p in B2B_CRYPTO_DEFINITIONS["ipsec_profiles"]:
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
            if name in existing:
                self.ipsec_prof_ids[name] = existing[name]
                self.stats["profiles_reused"] += 1
                print(f"  [EXISTE] IPsec Profile '{name}' (ID: {existing[name]})")
            else:
                if self.dry_run:
                    print(f"  [DRY-RUN] Crearía IPsec Profile '{name}'")
                    self.ipsec_prof_ids[name] = 8885
                    self.stats["profiles_created"] += 1
                else:
                    res = self.nb.post("vpn/ipsec-profiles", payload)
                    self.ipsec_prof_ids[name] = res["id"]
                    self.stats["profiles_created"] += 1
                    print(f"  [OK] IPsec Profile creado: '{name}' (ID: {res['id']})")
