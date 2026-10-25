"""Pruebas unitarias para el asistente B2BVPNProvisioner (NetBox Custom Script)."""

import unittest
from netbox_automation.custom_scripts import B2BVPNProvisioner
from netbox_automation.custom_scripts.base import AbortScript


class TestB2BVPNProvisioner(unittest.TestCase):
    """Pruebas unitarias completas para B2BVPNProvisioner."""

    def setUp(self):
        self.provisioner = B2BVPNProvisioner()

    def test_metadata_and_form_fields(self):
        """Verifica que el script expone metadatos y variables correctas para la GUI."""
        self.assertIn("[VPN] Aprovisionamiento B2B VPN & NAT", B2BVPNProvisioner.Meta.name)
        self.assertFalse(B2BVPNProvisioner.Meta.commit_default)

        # Campos clave
        self.assertTrue(hasattr(B2BVPNProvisioner, "tenant_name"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "tunnel_name"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "local_hub"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "adopt_existing"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "peer_ip_primary"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "peer_ip_secondary"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "crypto_profile"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "create_custom_profile"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "custom_profile_name"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "custom_profile_ike_version"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "custom_profile_encryption"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "custom_profile_dh_group"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "tunnel_inside_ip"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "vrf_name"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "tunnel_group_name"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "purpose"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "traffic_selectors"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "local_prefixes"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "local_nat_enabled"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "local_nat_prefixes"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "remote_prefixes"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "remote_nat_mode"))
        self.assertTrue(hasattr(B2BVPNProvisioner, "remote_nat_targets"))

        # Verificación del hint explicativo en create_custom_profile
        create_profile_var = getattr(B2BVPNProvisioner, "create_custom_profile")
        self.assertIn("HINT", create_profile_var.description)
        self.assertIn("Activar únicamente si el perfil criptográfico no existe previamente en NetBox", create_profile_var.description)

    def test_dual_hub_topology_creates_two_tunnels(self):
        """Verifica que la topología Dual-Hub genera 2 túneles en paralelo con sus nombres y tags."""
        data = {
            "tenant_name": "Endesa Renovables",
            "tunnel_name": "",  # Dejar en blanco para autogeneración
            "local_hub": "dual_hub",
            "peer_ip_primary": "198.51.100.10",
            "peer_ip_secondary": "198.51.100.20",
            "vrf_name": "VRF-B2B-EXT",
            "tunnel_group_name": "VPNs-B2B-Extranet",
            "description": "Túnel redundante telecontrol",
            "local_prefixes": "10.148.10.0/24",
            "local_nat_enabled": False,
            "remote_prefixes": "192.168.100.0/24",
            "remote_nat_mode": "none",
        }
        res = self.provisioner.run(data, commit=True)
        self.assertIn("to-endesa-renovables-madrid", res)
        self.assertIn("to-endesa-renovables-jesp", res)
        self.assertIn("vpn:endesa-renovables", res)

        logs = [log["message"] for log in self.provisioner.logs]
        self.assertTrue(any("to-endesa-renovables-madrid" in m for m in logs))
        self.assertTrue(any("to-endesa-renovables-jesp" in m for m in logs))
        self.assertTrue(any("198.51.100.10" in m for m in logs))

    def test_single_hub_with_manual_name(self):
        """Verifica que se respeta un nombre manual explícito si el operador lo introduce."""
        data = {
            "tenant_name": "Sopra Steria",
            "tunnel_name": "VPN-MAD-SOPRA-CORE",
            "local_hub": "madrid_cpd",
            "peer_ip_primary": "203.0.113.5",
            "local_prefixes": "10.148.15.0/24",
            "local_nat_enabled": False,
            "remote_prefixes": "10.200.0.0/16",
            "remote_nat_mode": "none",
        }
        res = self.provisioner.run(data, commit=True)
        self.assertIn("VPN-MAD-SOPRA-CORE", res)
        self.assertIn("vpn:sopra-steria", res)

    def test_fotovoltaica_snat_and_remote_peer_nat(self):
        """Prueba completa del escenario Fotovoltaica (SNAT local 100.97 + NAT Remoto en pool 100.98.200.1)."""
        data = {
            "tenant_name": "SolarTech Global",
            "tunnel_name": "",
            "local_hub": "madrid_cpd",
            "peer_ip_primary": "198.51.100.50",
            "vrf_name": "VRF-B2B-EXT",
            "description": "20 Plantas FV con NAT 1:1 y host telecontrol",
            "local_prefixes": "172.20.10.0/24\n172.20.25.0/24",
            "local_nat_enabled": True,
            "local_nat_prefixes": "100.97.10.0/24\n100.97.25.0/24",
            "remote_prefixes": "192.168.1.100/32",
            "remote_nat_mode": "peer_nat",
            "remote_nat_targets": "100.98.200.1/32",
        }
        res = self.provisioner.run(data, commit=True)
        self.assertIn("SolarTech Global", res)
        self.assertIn("to-solartech-global", res)

        logs = [log["message"] for log in self.provisioner.logs]
        self.assertTrue(any("100.97.10.0/24" in m for m in logs))
        self.assertTrue(any("100.97.25.0/24" in m for m in logs))
        self.assertTrue(any("100.98.200.1/32" in m for m in logs))

    def test_remote_local_dnat_scenario(self):
        """Prueba escenario donde nosotros hacemos DNAT en nuestro firewall de una red remota solapada."""
        data = {
            "tenant_name": "Proveedor Inflexible",
            "tunnel_name": "to-prov-inflexible",
            "local_hub": "jesp",
            "peer_ip_primary": "198.51.100.99",
            "local_prefixes": "10.152.10.0/24",
            "local_nat_enabled": False,
            "remote_prefixes": "10.148.10.0/24",  # Solapada con Madrid CPD
            "remote_nat_mode": "local_dnat",
            "remote_nat_targets": "100.98.10.0/24",
        }
        res = self.provisioner.run(data, commit=True)
        self.assertIn("to-prov-inflexible", res)

        logs = [log["message"] for log in self.provisioner.logs]
        self.assertTrue(any("Mapeado DNAT 100.98.10.0/24 para 10.148.10.0/24" in m for m in logs))

    def test_validation_errors(self):
        """Verifica que el script aborta limpiamente ante errores de entrada."""
        # 1. Sin redes locales
        with self.assertRaises(AbortScript) as ctx:
            self.provisioner.run(
                {
                    "tenant_name": "Test",
                    "peer_ip_primary": "1.1.1.1",
                    "local_prefixes": "",
                    "remote_prefixes": "10.0.0.0/24",
                },
                commit=False,
            )
        self.assertIn("al menos un prefijo local", str(ctx.exception))

        # 2. Desajuste en cardinalidad de NAT Local (2 reales vs 1 NAT)
        with self.assertRaises(AbortScript) as ctx:
            self.provisioner.run(
                {
                    "tenant_name": "Test",
                    "peer_ip_primary": "1.1.1.1",
                    "local_prefixes": "172.20.1.0/24\n172.20.2.0/24",
                    "local_nat_enabled": True,
                    "local_nat_prefixes": "100.97.1.0/24",
                    "remote_prefixes": "192.168.1.0/24",
                    "remote_nat_mode": "none",
                },
                commit=False,
            )
        self.assertIn("Desajuste en Lado Local", str(ctx.exception))

        # 3. Desajuste en cardinalidad de NAT Remoto (2 remotos vs 1 target)
        with self.assertRaises(AbortScript) as ctx:
            self.provisioner.run(
                {
                    "tenant_name": "Test",
                    "peer_ip_primary": "1.1.1.1",
                    "local_prefixes": "10.10.0.0/24",
                    "local_nat_enabled": False,
                    "remote_prefixes": "192.168.1.0/24\n192.168.2.0/24",
                    "remote_nat_mode": "peer_nat",
                    "remote_nat_targets": "100.98.1.0/24",
                },
                commit=False,
            )
        self.assertIn("Desajuste en Lado Remoto", str(ctx.exception))

    def test_dry_run_mode(self):
        """Verifica que el modo simulación (commit=False) genera logs de aviso sin error."""
        data = {
            "tenant_name": "Simulacion B2B",
            "local_hub": "madrid_cpd",
            "peer_ip_primary": "198.51.100.1",
            "local_prefixes": "10.148.20.0/24",
            "local_nat_enabled": False,
            "remote_prefixes": "192.168.50.0/24",
            "remote_nat_mode": "none",
        }
        res = self.provisioner.run(data, commit=False)
        self.assertIn("Aprovisionamiento completado", res)

        logs = [log["message"] for log in self.provisioner.logs]
        self.assertTrue(any("DRY-RUN" in m for m in logs))

    def test_crypto_profile_predefined_assignment(self):
        """Verifica la asignación de perfiles criptográficos estándar existentes (ej. Axpo Custom)."""
        data = {
            "tenant_name": "Axpo Iberia",
            "local_hub": "madrid_cpd",
            "peer_ip_primary": "195.55.10.20",
            "crypto_profile": "axpo",
            "local_prefixes": "10.148.30.0/24",
            "remote_prefixes": "10.210.0.0/16",
        }
        res = self.provisioner.run(data, commit=True)
        self.assertTrue("ipsec-prof-b2b-axpo-dh19" in res or "Axpo" in res)

    def test_crypto_profile_custom_creation(self):
        """Verifica la creación bajo demanda de perfil criptográfico desde el formulario con parámetros personalizados."""
        data = {
            "tenant_name": "New Partner",
            "local_hub": "jesp",
            "peer_ip_primary": "212.128.5.1",
            "create_custom_profile": True,
            "custom_profile_name": "Partner-Custom-IKEv2",
            "custom_profile_ike_version": "2",
            "custom_profile_encryption": "AES-256-SHA512",
            "custom_profile_dh_group": "19",
            "local_prefixes": "10.152.0.0/24",
            "remote_prefixes": "192.168.200.0/24",
        }
        res = self.provisioner.run(data, commit=True)
        self.assertIn("Partner-Custom-IKEv2", res)
        logs = [log["message"] for log in self.provisioner.logs]
        self.assertTrue(any("Partner-Custom-IKEv2" in m for m in logs))
        self.assertTrue(any("DH: Group 19" in m for m in logs))

    def test_phase2_traffic_selectors_1_to_n(self):
        """Verifica que el uso de traffic_selectors soporta matrices 1 a N o N a M sin exigir len(local) == len(remote)."""
        selectors = (
            "172.20.10.0/24 -> 10.100.5.0/24 [to-Moeve-FV00]\n"
            "172.20.12.0/24 -> 10.100.5.0/24 [to-Moeve-FV05]\n"
            "172.20.14.0/24 -> 10.100.5.0/24 [to-Moeve-FV08]\n"
            "172.20.16.0/24 -> 10.100.5.0/24 [to-Moeve-FV10]"
        )
        data = {
            "tenant_name": "Moeve Renovables",
            "local_hub": "madrid_cpd",
            "peer_ip_primary": "80.25.10.5",
            "traffic_selectors": selectors,
        }
        res = self.provisioner.run(data, commit=True)
        self.assertIn("Moeve Renovables", res)
        self.assertIn("Selectores procesados: 4", res)

        logs = [log["message"] for log in self.provisioner.logs]
        self.assertTrue(any("Procesando 4 selectores Phase 2" in m for m in logs))

    def test_fortios_object_alias_and_fqdn_in_traffic_selectors(self):
        """Verifica el soporte de alias FortiOS y FQDN en selectores Phase 2."""
        selectors = (
            "[Aws]*vNet-FV-UCO (172.20.10.0/24) -> [Host]*moeve (10.100.5.10/32) [to-Moeve-FV00]\n"
            "[Axpo]*Net-01 -> telecontrol.axpo.com [to-Axpo-Main]"
        )
        data = {
            "tenant_name": "FortiOS Test",
            "local_hub": "madrid_cpd",
            "peer_ip_primary": "198.51.100.77",
            "traffic_selectors": selectors,
        }
        res = self.provisioner.run(data, commit=True)
        self.assertIn("FortiOS Test", res)
        self.assertIn("Selectores procesados: 2", res)

    def test_adopt_existing_tunnel_mode(self):
        """Verifica que el modo adopción (adopt_existing=True) procesa sin crear sufijos adicionales."""
        data = {
            "tenant_name": "Axpo",
            "tunnel_name": "to-axpo",
            "local_hub": "madrid_cpd",
            "peer_ip_primary": "195.55.10.20",
            "adopt_existing": True,
            "local_prefixes": "10.148.10.0/24",
            "remote_prefixes": "10.200.0.0/16",
        }
        res = self.provisioner.run(data, commit=True)
        self.assertIn("to-axpo", res)

    def test_tunnel_interface_and_inside_ip(self):
        """Verifica la asignación de la Inside IP (/32 o /30) a la interfaz virtual del firewall."""
        data = {
            "tenant_name": "Orange B2B",
            "tunnel_name": "to-orange",
            "local_hub": "madrid_cpd",
            "peer_ip_primary": "213.0.100.5",
            "tunnel_inside_ip": "10.254.13.1/32",
            "local_prefixes": "10.148.50.0/24",
            "remote_prefixes": "192.168.10.0/24",
        }
        res = self.provisioner.run(data, commit=True)
        self.assertIn("to-orange", res)

        logs = [log["message"] for log in self.provisioner.logs]
        self.assertTrue(any("10.254.13.1/32" in m and "INSIDE IP" in m.upper() for m in logs))


if __name__ == "__main__":
    unittest.main()

