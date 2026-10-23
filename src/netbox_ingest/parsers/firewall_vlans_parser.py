"""Parser para extraer las VLANs reales desde inputs/vlans_firewalls_consolidadas.md."""

import re
from pathlib import Path
from typing import Any, Dict, List


def parse_firewall_vlans(markdown_path: Path) -> List[Dict[str, Any]]:
    """Parsea el archivo markdown de VLANs de firewalls y devuelve la lista de dispositivos con sus VLANs."""
    text = markdown_path.read_text(encoding="utf-8")
    
    # Separar por secciones de dispositivo
    # Formato: ### ALIAS (`DEVICE_NAME`)
    device_sections = re.findall(
        r"###\s+([A-Za-z0-9_\-]+)\s+\(`([A-Za-z0-9_\-]+)`\)\s*\n"
        r"-\s+\*\*ADOM\*\*:\s*`([^`]+)`\s*\|\s*\*\*IP Gestión\*\*:\s*`([^`]+)`\s*\n\s*"
        r"\|[^\n]+\n\|[^\n]+\n((?:\|[^\n]+\n?)+)",
        text
    )

    parsed_devices = []
    
    for alias, device_name, adom, mgmt_ip, table_block in device_sections:
        vlans = []
        for line in table_block.strip().splitlines():
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 7:
                interface, vid_str, gw_ip, mask, cidr, ip_range, desc = parts[:7]
                # Extraer número de VID
                vid_clean = re.sub(r"[^\d]", "", vid_str)
                if not vid_clean:
                    continue
                vid = int(vid_clean)
                vlans.append({
                    "interface": interface.replace("`", ""),
                    "vid": vid,
                    "gateway_ip": gw_ip.replace("`", ""),
                    "mask": mask.replace("`", ""),
                    "cidr": cidr.replace("`", ""),
                    "ip_range": ip_range.replace("`", ""),
                    "alias": desc.replace("`", "") if desc else "",
                })
        
        parsed_devices.append({
            "alias": alias,
            "device_name": device_name,
            "adom": adom,
            "mgmt_ip": mgmt_ip,
            "vlans": vlans,
        })
        
    return parsed_devices


if __name__ == "__main__":
    md_file = Path("/home/carlos/projects-ag/infra-netbox-management/inputs/vlans_firewalls_consolidadas.md")
    devices = parse_firewall_vlans(md_file)
    print(f"Dispositivos parseados: {len(devices)}")
    total_vlans = sum(len(d['vlans']) for d in devices)
    print(f"Total VLANs parseadas: {total_vlans}")
    for d in devices:
        print(f" - {d['alias']} ({d['device_name']}): {len(d['vlans'])} VLANs")
