"""Cliente de comunicación y conciliación idempotente con la API de NetBox."""

import os
import json
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error
import urllib.parse


class NetBoxClient:
    """Cliente HTTP ligero para la API REST de NetBox (stdlib urllib)."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        self.base_url = (base_url or os.getenv("NETBOX_URL", "https://netbox.infra.edison.es")).rstrip("/")
        self.token = token or os.getenv("NETBOX_TOKEN", "")

    def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/{endpoint.strip('/')}/"
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Token {self.token}"

        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            raise RuntimeError(f"HTTP {e.code} en {url}: {err_body}") from e

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", endpoint, data=data)

    def patch(self, endpoint: str, object_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PATCH", f"{endpoint.strip('/')}/{object_id}", data=data)
