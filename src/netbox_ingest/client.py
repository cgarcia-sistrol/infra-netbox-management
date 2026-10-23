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
        # Auto-cargar .env si existe en el directorio de trabajo
        env_path = os.path.join(os.getcwd(), ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if "=" in line and not line.startswith("#"):
                            k, v = line.split("=", 1)
                            if k.strip() not in os.environ:
                                os.environ[k.strip()] = v.strip()
            except Exception:
                pass

        self.base_url = (base_url or os.getenv("NETBOX_URL", "https://netbox.infra.edison.es")).rstrip("/")
        self.token = token or os.getenv("NETBOX_TOKEN", "")

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
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

        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            raise RuntimeError(f"HTTP {e.code} en {url}: {err_body}") from e

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", endpoint, data=data)

    def patch(self, endpoint: str, object_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PATCH", f"{endpoint.strip('/')}/{object_id}", data=data)

    def delete(self, endpoint: str, object_id: int) -> None:
        self._request("DELETE", f"{endpoint.strip('/')}/{object_id}")

    def get_all(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Obtiene todos los registros paginados de un endpoint."""
        results: List[Dict[str, Any]] = []
        offset = 0
        limit = 100
        current_params = dict(params or {})
        current_params["limit"] = limit

        while True:
            current_params["offset"] = offset
            response = self.get(endpoint, params=current_params)
            batch = response.get("results", [])
            results.extend(batch)
            if not response.get("next") or len(batch) == 0:
                break
            offset += len(batch)

        return results

    def get_by_slug(self, endpoint: str, slug: str) -> Optional[Dict[str, Any]]:
        """Busca un objeto único por slug."""
        res = self.get(endpoint, params={"slug": slug})
        results = res.get("results", [])
        return results[0] if results else None

    def get_or_create(self, endpoint: str, unique_key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Crea un objeto si no existe basándose en una clave única (p.e. slug o name)."""
        val = data.get(unique_key)
        if val is not None:
            existing = self.get(endpoint, params={unique_key: val})
            results = existing.get("results", [])
            if results:
                return results[0]

        return self.post(endpoint, data)
