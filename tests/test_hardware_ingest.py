"""Pruebas unitarias para el catálogo de hardware y módulo de ingesta de Fase 1."""

import unittest
from netbox_ingest.hardware_definitions import (
    MANUFACTURERS,
    DEVICE_ROLES,
    PLATFORMS,
    DEVICE_TYPES,
)
from netbox_ingest.hardware_parser import (
    validate_hardware_catalog,
    get_catalog_summary,
)


class TestHardwareDefinitions(unittest.TestCase):
    """Pruebas de integridad del catálogo de hardware."""

    def test_manufacturers_count(self):
        # 6 de lista inicial + Netgear
        self.assertEqual(len(MANUFACTURERS), 7)
        slugs = {m["slug"] for m in MANUFACTURERS}
        expected = {"fortinet", "teltonika", "ubiquiti", "tp-link", "d-link", "milesight", "netgear"}
        self.assertEqual(slugs, expected)

    def test_roles_count(self):
        self.assertEqual(len(DEVICE_ROLES), 6)
        slugs = {r["slug"] for r in DEVICE_ROLES}
        expected = {"firewall", "switch", "cellular-router", "wireless-ap", "wireless-router", "management"}
        self.assertEqual(slugs, expected)

    def test_platforms_count(self):
        self.assertEqual(len(PLATFORMS), 4)
        slugs = {p["slug"] for p in PLATFORMS}
        expected = {"fortios", "fortiswitchos", "rutos", "unifi"}
        self.assertEqual(slugs, expected)

    def test_device_types_count(self):
        self.assertEqual(len(DEVICE_TYPES), 25)

    def test_validate_catalog_success(self):
        mfgs, roles, plats, dts = validate_hardware_catalog()
        self.assertEqual(len(mfgs), 7)
        self.assertEqual(len(roles), 6)
        self.assertEqual(len(plats), 4)
        self.assertEqual(len(dts), 25)

    def test_catalog_summary_counts(self):
        summary = get_catalog_summary()
        self.assertEqual(summary["manufacturers_count"], 7)
        self.assertEqual(summary["roles_count"], 6)
        self.assertEqual(summary["platforms_count"], 4)
        self.assertEqual(summary["device_types_count"], 25)
        self.assertGreater(summary["total_interfaces"], 150)
        self.assertGreater(summary["total_console_ports"], 5)
        self.assertGreater(summary["total_power_ports"], 5)

    def test_fortinet_models_presence(self):
        fortinet_models = [dt for dt in DEVICE_TYPES if dt["manufacturer_slug"] == "fortinet"]
        self.assertEqual(len(fortinet_models), 9)
        slugs = {dt["slug"] for dt in fortinet_models}
        expected = {
            "fortigate-100f",
            "fortigate-60f",
            "fortigate-80f",
            "fortimanager-vm-s-series",
            "fortiswitch-124f",
            "fortiswitch-224e",
            "fortiswitch-224e-poe",
            "fortiswitch-248d",
            "fortiswitch-248e-poe",
        }
        self.assertEqual(slugs, expected)

    def test_teltonika_models_presence(self):
        teltonika_models = [dt for dt in DEVICE_TYPES if dt["manufacturer_slug"] == "teltonika"]
        self.assertEqual(len(teltonika_models), 4)
        slugs = {dt["slug"] for dt in teltonika_models}
        expected = {"rut600", "rut601", "rut241", "rutx11"}
        self.assertEqual(slugs, expected)

    def test_ubiquiti_models_presence(self):
        ubiquiti_models = [dt for dt in DEVICE_TYPES if dt["manufacturer_slug"] == "ubiquiti"]
        self.assertEqual(len(ubiquiti_models), 6)
        slugs = {dt["slug"] for dt in ubiquiti_models}
        expected = {"u6-mesh", "u7-outdoor", "u6-lr", "u7-pro", "unifi-ap-ac-lr", "unifi-ap-ac-pro"}
        self.assertEqual(slugs, expected)

    def test_tplink_models_presence(self):
        tplink_models = [dt for dt in DEVICE_TYPES if dt["manufacturer_slug"] == "tp-link"]
        self.assertEqual(len(tplink_models), 3)
        slugs = {dt["slug"] for dt in tplink_models}
        expected = {"archer-c6", "archer-mr600", "archer-a6"}
        self.assertEqual(slugs, expected)

    def test_dlink_models_presence(self):
        dlink_models = [dt for dt in DEVICE_TYPES if dt["manufacturer_slug"] == "d-link"]
        self.assertEqual(len(dlink_models), 1)
        self.assertEqual(dlink_models[0]["slug"], "dap-2662")

    def test_milesight_models_presence(self):
        milesight_models = [dt for dt in DEVICE_TYPES if dt["manufacturer_slug"] == "milesight"]
        self.assertEqual(len(milesight_models), 2)
        slugs = {dt["slug"] for dt in milesight_models}
        expected = {"ur32", "ur32l"}
        self.assertEqual(slugs, expected)
