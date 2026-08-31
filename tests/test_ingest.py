"""Pruebas unitarias para el módulo de ingesta y parsing de ubicaciones NetBox."""

import os
import unittest

from netbox_ingest.parser import (
    slugify,
    format_address,
    format_comments,
    parse_locations_file,
    EXCLUDED_LOCATION_IDS,
    CUSTOM_FIELDS,
    TENANT_INFO,
)

INPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "inputs", "fresh-locations.json")


class TestSlugify(unittest.TestCase):
    """Pruebas unitarias para la función de generación de slugs."""

    def test_slugify_accents_and_spaces(self):
        # Arrange
        text = "Oficina Madrid - Esplandiú"
        # Act
        result = slugify(text)
        # Assert
        self.assertEqual(result, "oficina-madrid-esplandiu")

    def test_slugify_special_characters(self):
        # Arrange
        text = "Marina D'Or (Castellón)"
        # Act
        result = slugify(text)
        # Assert
        self.assertEqual(result, "marina-dor-castellon")


class TestParser(unittest.TestCase):
    """Pruebas para el parser del archivo de ubicaciones de Freshservice."""

    @classmethod
    def setUpClass(cls):
        cls.tenant, cls.regions, cls.sites = parse_locations_file(INPUT_FILE)

    def test_tenant_info(self):
        # Assert
        self.assertEqual(self.tenant["name"], "Edison Next Spain")
        self.assertEqual(self.tenant["slug"], "edison-next-spain")

    def test_regions_count(self):
        # Assert
        self.assertEqual(len(self.regions), 9)
        region_slugs = {r["slug"] for r in self.regions}
        expected_slugs = {
            "central",
            "b2b-northeast",
            "b2g-northeast",
            "levante",
            "mid-north",
            "mid-south",
            "north",
            "northwest",
            "root",
        }
        self.assertEqual(region_slugs, expected_slugs)

    def test_sites_total_count(self):
        # Assert
        self.assertEqual(len(self.sites), 81)

    def test_excluded_locations_not_present(self):
        # Assert
        site_fresh_ids = {s["freshservice_id"] for s in self.sites}
        for excluded_id in EXCLUDED_LOCATION_IDS:
            self.assertNotIn(excluded_id, site_fresh_ids)

    def test_maintained_root_locations_present(self):
        # Assert
        sites_by_name = {s["name"]: s for s in self.sites}
        self.assertIn("Oficina Madrid - Esplandiú", sites_by_name)
        self.assertEqual(sites_by_name["Oficina Madrid - Esplandiú"]["region_slug"], "root")
        self.assertIn("Oficina Gijón", sites_by_name)
        self.assertEqual(sites_by_name["Oficina Gijón"]["region_slug"], "root")
        self.assertIn("SAT Fontventa", sites_by_name)
        self.assertEqual(sites_by_name["SAT Fontventa"]["region_slug"], "root")

    def test_custom_fields_initial_state(self):
        # Assert
        for s in self.sites:
            self.assertIn("alias", s["custom_fields"])
            self.assertIn("alias_infra", s["custom_fields"])
            self.assertEqual(s["custom_fields"]["alias"], "")
            self.assertEqual(s["custom_fields"]["alias_infra"], "")

    def test_custom_fields_definitions(self):
        # Assert
        self.assertEqual(len(CUSTOM_FIELDS), 2)
        names = {cf["name"] for cf in CUSTOM_FIELDS}
        self.assertEqual(names, {"alias", "alias_infra"})


if __name__ == "__main__":
    unittest.main()
