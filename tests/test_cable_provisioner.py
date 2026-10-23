"""Pruebas unitarias para el motor genérico de provisión de cableado (CableProvisioner)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from netbox_automation.dcim.cable_provisioner import CableProvisioner


class TestCableProvisioner(unittest.TestCase):
    """Test suite siguiendo patrón Arrange-Act-Assert (AAA)."""

    def setUp(self):
        self.mock_client = MagicMock()
        self.provisioner = CableProvisioner(client=self.mock_client)

    def test_load_specification_valid(self):
        # Arrange
        data = {
            "site": "Test Site",
            "cables": [
                {
                    "side_a": {"device": "SW1", "interface": "port1"},
                    "side_b": {"device": "SW2", "interface": "port2"},
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Act
            spec = self.provisioner.load_specification(temp_path)
            # Assert
            self.assertEqual(spec["site"], "Test Site")
            self.assertEqual(len(spec["cables"]), 1)
        finally:
            Path(temp_path).unlink()

    def test_load_specification_invalid(self):
        # Arrange
        data = {"site": "Missing Cables"}
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Act & Assert
            with self.assertRaises(ValueError):
                self.provisioner.load_specification(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_ensure_interfaces_existing(self):
        # Arrange
        self.mock_client.get.side_effect = [
            {"results": [{"id": 10, "name": "SRV1"}]},  # dcim/devices
            {"results": [{"id": 101, "name": "nic1"}]},  # dcim/interfaces
        ]
        spec = [{"device": "SRV1", "name": "nic1"}]

        # Act
        actions = self.provisioner.ensure_interfaces(spec, dry_run=False)

        # Assert
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action"], "EXISTS")
        self.assertEqual(actions[0]["id"], 101)
        self.mock_client.post.assert_not_called()

    def test_ensure_interfaces_create_in_real_mode(self):
        # Arrange
        self.mock_client.get.side_effect = [
            {"results": [{"id": 10, "name": "SRV1"}]},  # dcim/devices
            {"results": []},  # dcim/interfaces (no existe)
        ]
        self.mock_client.post.return_value = {"id": 202, "name": "nic1"}
        spec = [{"device": "SRV1", "name": "nic1", "type": "1000base-t"}]

        # Act
        actions = self.provisioner.ensure_interfaces(spec, dry_run=False)

        # Assert
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action"], "CREATED")
        self.assertEqual(actions[0]["id"], 202)
        self.mock_client.post.assert_called_once_with(
            "dcim/interfaces",
            {"device": 10, "name": "nic1", "type": "1000base-t", "description": ""},
        )

    def test_provision_cables_dry_run(self):
        # Arrange
        spec = {
            "site": "Test Site",
            "cables": [
                {
                    "side_a": {"device": "SW1", "interface": "port1"},
                    "side_b": {"device": "SW2", "interface": "port2"},
                    "type": "cat6",
                    "status": "connected",
                    "label": "CAB-01",
                }
            ],
        }
        self.mock_client.get.side_effect = [
            {"results": [{"id": 1, "name": "SW1"}]},  # dev SW1
            {"results": [{"id": 11, "name": "port1", "cable": None}]},  # intf SW1:port1
            {"results": [{"id": 2, "name": "SW2"}]},  # dev SW2
            {"results": [{"id": 22, "name": "port2", "cable": None}]},  # intf SW2:port2
        ]

        # Act
        summary = self.provisioner.provision_cables(spec, dry_run=True)

        # Assert
        self.assertEqual(len(summary["created"]), 1)
        self.assertEqual(summary["created"][0]["status"], "PLANNED")
        self.assertEqual(len(summary["skipped"]), 0)
        self.mock_client.post.assert_not_called()

    def test_provision_cables_real_mode(self):
        # Arrange
        spec = {
            "site": "Test Site",
            "cables": [
                {
                    "side_a": {"device": "SW1", "interface": "port1"},
                    "side_b": {"device": "SW2", "interface": "port2"},
                    "type": "cat6",
                    "status": "connected",
                    "label": "CAB-01",
                    "description": "Enlace de prueba",
                }
            ],
        }
        self.mock_client.get.side_effect = [
            {"results": [{"id": 1, "name": "SW1"}]},
            {"results": [{"id": 11, "name": "port1", "cable": None}]},
            {"results": [{"id": 2, "name": "SW2"}]},
            {"results": [{"id": 22, "name": "port2", "cable": None}]},
        ]
        self.mock_client.post.return_value = {"id": 999}

        # Act
        summary = self.provisioner.provision_cables(spec, dry_run=False)

        # Assert
        self.assertEqual(len(summary["created"]), 1)
        self.assertEqual(summary["created"][0]["status"], "CREATED")
        self.assertEqual(summary["created"][0]["cable_id"], 999)
        self.mock_client.post.assert_called_once_with(
            "dcim/cables",
            {
                "a_terminations": [{"object_type": "dcim.interface", "object_id": 11}],
                "b_terminations": [{"object_type": "dcim.interface", "object_id": 22}],
                "type": "cat6",
                "status": "connected",
                "label": "CAB-01",
                "description": "Enlace de prueba",
            },
        )

    def test_provision_cables_idempotent_skip(self):
        # Arrange
        spec = {
            "site": "Test Site",
            "cables": [
                {
                    "side_a": {"device": "SW1", "interface": "port1"},
                    "side_b": {"device": "SW2", "interface": "port2"},
                }
            ],
        }
        # Ambos extremos ya comparten el cable ID 500
        self.mock_client.get.side_effect = [
            {"results": [{"id": 1, "name": "SW1"}]},
            {"results": [{"id": 11, "name": "port1", "cable": {"id": 500}}]},
            {"results": [{"id": 2, "name": "SW2"}]},
            {"results": [{"id": 22, "name": "port2", "cable": {"id": 500}}]},
        ]

        # Act
        summary = self.provisioner.provision_cables(spec, dry_run=False)

        # Assert
        self.assertEqual(len(summary["created"]), 0)
        self.assertEqual(len(summary["skipped"]), 1)
        self.assertEqual(summary["skipped"][0]["cable_id"], 500)
        self.mock_client.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
