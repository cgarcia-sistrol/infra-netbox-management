"""Pruebas unitarias para los Asistentes Operativos Nativos de NetBox (Custom Scripts)."""

import unittest
from netbox_automation.custom_scripts import (
    DeviceWizard,
    IPAMQuickAllocate,
    DeviceLifecycle,
)
from netbox_automation.custom_scripts.base import (
    Site,
    DeviceRole,
    DeviceType,
    Device,
    Interface,
    Prefix,
    Cable,
    AbortScript,
)


class TestDeviceWizard(unittest.TestCase):
    """Pruebas para el asistente DeviceWizard."""

    def setUp(self):
        self.wizard = DeviceWizard()
        self.site = Site(name="Oficina Madrid - Esplandiu", slug="oficina-madrid-esplandiu")
        self.role = DeviceRole(name="Switch", slug="switch")
        self.device_type = DeviceType(model="FortiSwitch-148F", slug="fortiswitch-148f")
        self.prefix = Prefix(prefix="10.10.80.0/24", site=self.site, _next_ip="10.10.80.25/24")

    def test_metadata_and_form_fields(self):
        """Verifica que el script expone metadatos y variables correctas para la GUI."""
        self.assertIn("1. Alta de Dispositivo", DeviceWizard.Meta.name)
        self.assertFalse(DeviceWizard.Meta.commit_default)
        self.assertTrue(hasattr(DeviceWizard, "site"))
        self.assertTrue(hasattr(DeviceWizard, "device_role"))
        self.assertTrue(hasattr(DeviceWizard, "device_type"))
        self.assertTrue(hasattr(DeviceWizard, "device_name"))
        self.assertTrue(hasattr(DeviceWizard, "prefix"))
        self.assertTrue(hasattr(DeviceWizard, "specific_ip"))

    def test_run_dry_run_with_auto_ip(self):
        """Prueba simulación (dry-run) con resolución automática de IP libre."""
        data = {
            "site": self.site,
            "device_role": self.role,
            "device_type": self.device_type,
            "device_name": "SW-ESPLAN-05",
            "serial": "FS148F12345678",
            "asset_tag": "ACT-1005",
            "interface_name": "mgmt0",
            "prefix": self.prefix,
            "specific_ip": None,
            "status": "active",
            "comments": "Switch de distribución",
        }
        res = self.wizard.run(data, commit=False)
        self.assertIn("SW-ESPLAN-05", res)
        self.assertIn("10.10.80.25/24", res)

        logs = [log["message"] for log in self.wizard.logs]
        self.assertTrue(any("SIMULACIÓN (DRY-RUN)" in m for m in logs))
        self.assertTrue(any("Auto-reservada próxima IP libre" in m for m in logs))

    def test_run_commit_with_manual_ip(self):
        """Prueba ejecución real (commit=True) con dirección IP manual."""
        data = {
            "site": self.site,
            "device_role": self.role,
            "device_type": self.device_type,
            "device_name": "SW-ESPLAN-06",
            "serial": "FS148F99999",
            "interface_name": "eth0",
            "prefix": None,
            "specific_ip": "10.10.80.50/24",
            "status": "planned",
        }
        res = self.wizard.run(data, commit=True)
        self.assertIn("10.10.80.50/24", res)
        logs = [log["message"] for log in self.wizard.logs]
        self.assertTrue(any("PRODUCCIÓN" in m for m in logs))
        self.assertTrue(any("IP manual" in m for m in logs))


class TestIPAMQuickAllocate(unittest.TestCase):
    """Pruebas para el asistente IPAMQuickAllocate."""

    def setUp(self):
        self.allocator = IPAMQuickAllocate()
        self.prefix = Prefix(prefix="10.20.10.0/24", _next_ip="10.20.10.42/24")
        self.device = Device(name="PRINTER-CORP-01")

    def test_metadata_and_form_fields(self):
        """Verifica metadatos y campos de formulario."""
        self.assertIn("1. Reserva Rápida IPAM", IPAMQuickAllocate.Meta.name)
        self.assertTrue(hasattr(IPAMQuickAllocate, "prefix"))
        self.assertTrue(hasattr(IPAMQuickAllocate, "purpose"))
        self.assertTrue(hasattr(IPAMQuickAllocate, "device"))
        self.assertTrue(hasattr(IPAMQuickAllocate, "interface_name"))

    def test_run_allocate_with_device(self):
        """Prueba reserva asociando a un dispositivo."""
        data = {
            "prefix": self.prefix,
            "purpose": "Impresora Planta 2",
            "dns_name": "printer-p2.infra.edison.es",
            "status": "reserved",
            "device": self.device,
            "interface_name": "eth0",
            "set_as_primary": True,
        }
        res = self.allocator.run(data, commit=True)
        self.assertIn("10.20.10.42/24", res)
        self.assertEqual(self.device.primary_ip4.address, "10.20.10.42/24")

    def test_run_prefix_exhausted(self):
        """Verifica que lanza AbortScript si el prefijo no tiene IPs disponibles."""
        empty_prefix = Prefix(prefix="10.30.0.0/24", _next_ip=None)
        data = {
            "prefix": empty_prefix,
            "purpose": "Test Fallo",
        }
        with self.assertRaises(AbortScript):
            self.allocator.run(data, commit=False)


class TestDeviceLifecycle(unittest.TestCase):
    """Pruebas para el asistente DeviceLifecycle."""

    def setUp(self):
        self.lifecycle = DeviceLifecycle()
        self.site_a = Site(name="Sede A", slug="sede-a")
        self.site_b = Site(name="Sede B", slug="sede-b")
        self.device = Device(name="RTR-TEST-01", site=self.site_a, status="active")

    def test_metadata_and_form_fields(self):
        """Verifica metadatos y campos de formulario."""
        self.assertIn("2. Ciclo de Vida de Dispositivo", DeviceLifecycle.Meta.name)
        self.assertTrue(hasattr(DeviceLifecycle, "action"))
        self.assertTrue(hasattr(DeviceLifecycle, "device"))
        self.assertTrue(hasattr(DeviceLifecycle, "new_site"))

    def test_relocate_requires_new_site(self):
        """Verifica que la acción reubicar exige nueva sede."""
        data = {
            "action": "relocate",
            "device": self.device,
            "new_site": None,
        }
        with self.assertRaises(AbortScript):
            self.lifecycle.run(data, commit=False)

    def test_relocate_success(self):
        """Prueba reubicación limpia de sede."""
        data = {
            "action": "relocate",
            "device": self.device,
            "new_site": self.site_b,
            "disconnect_cables": True,
            "release_ips": True,
            "comments": "Traslado autorizado ticket INC-4921",
        }
        res = self.lifecycle.run(data, commit=True)
        self.assertEqual(self.device.site, self.site_b)
        self.assertIn("trasladado con éxito", res)
        self.assertIn("INC-4921", self.device.comments)

    def test_decommission_success(self):
        """Prueba paso a baja operativa (decommissioning)."""
        data = {
            "action": "decommission",
            "device": self.device,
            "comments": "Sustituido por renovación tecnológica",
        }
        res = self.lifecycle.run(data, commit=True)
        self.assertEqual(self.device.status, "decommissioning")
        self.assertIn("decommissioning", res)

    def test_purge_success(self):
        """Prueba eliminación definitiva de equipo."""
        data = {
            "action": "purge",
            "device": self.device,
        }
        res = self.lifecycle.run(data, commit=True)
        self.assertTrue(self.device._deleted)
        self.assertIn("purgado definitivamente", res)


if __name__ == "__main__":
    unittest.main()
