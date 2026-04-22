import aiohttp
import json
import time
import uuid
from urllib.parse import quote


class XUIError(Exception):
    pass


class XUIClient:
    def __init__(self, server: dict):
        self.server = server
        self.host = server["host"]
        self.port = server["port"]
        self.protocol = server.get("protocol", "https")

        path = server.get("web_base_path", "").strip("/")
        path = f"/{path}" if path else ""

        self.base_url = f"{self.protocol}://{self.host}:{self.port}{path}"
        self.session = None
        self.is_authenticated = False
        self._inbounds_cache = None

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(ssl=False)
            jar = aiohttp.CookieJar(unsafe=True)
            timeout = aiohttp.ClientTimeout(total=15)

            self.session = aiohttp.ClientSession(
                connector=connector,
                cookie_jar=jar,
                timeout=timeout,
            )
            self.is_authenticated = False
            self._inbounds_cache = None

        return self.session

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def login(self):
        session = await self._ensure_session()

        data = {
            "username": self.server["login"],
            "password": self.server["password"],
        }

        login_url = f"{self.base_url}/login"

        async with session.post(login_url, data=data) as response:
            text = await response.text()

            if response.status != 200:
                raise XUIError(f"Ошибка логина: HTTP {response.status}")

            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                raise XUIError("Панель вернула не JSON при логине")

            if result.get("success") is False:
                raise XUIError(result.get("msg", "Не удалось войти в панель"))

            self.is_authenticated = True
            return True

    async def _request(self, method: str, endpoint: str, data: dict | None = None):
        session = await self._ensure_session()

        if not self.is_authenticated and endpoint != "/login":
            await self.login()

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }

        async with session.request(method, url, json=data, headers=headers) as response:
            text = await response.text()

            if response.status != 200:
                raise XUIError(f"HTTP {response.status}: {text[:200]}")

            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                raise XUIError("Панель вернула не JSON")

            if result.get("success") is False:
                raise XUIError(result.get("msg", "Ошибка запроса к панели"))

            return result

    async def get_inbounds(self):
        if self._inbounds_cache is not None:
            return self._inbounds_cache

        result = await self._request("GET", "/panel/api/inbounds/list")
        self._inbounds_cache = result.get("obj", [])
        return self._inbounds_cache

    def _resolve_inbound_flow(self, inbound: dict) -> str:
        protocol = inbound.get("protocol", "")
        if protocol != "vless":
            return ""

        stream_raw = inbound.get("streamSettings", "{}")
        stream = json.loads(stream_raw) if isinstance(stream_raw, str) else stream_raw

        network = stream.get("network", "tcp")
        security = stream.get("security", "none")

        if network == "tcp" and security in ("reality", "tls"):
            return "xtls-rprx-vision"

        return ""

    async def get_inbound_flow(self, inbound_id: int) -> str:
        inbound = await self.get_inbound_by_id(inbound_id)
        return self._resolve_inbound_flow(inbound)

    async def add_client(
        self,
        inbound_id: int,
        email: str,
        total_gb: int = 0,
        expire_days: int = 30,
        limit_ip: int = 1,
        enable: bool = True,
        tg_id: str = "",
        flow: str = "",
    ):
        if expire_days <= 0:
            raise XUIError("expire_days должен быть больше 0")

        client_uuid = str(uuid.uuid4())
        expire_time = int((time.time() + expire_days * 86400) * 1000)
        total_bytes = total_gb * 1024 * 1024 * 1024 if total_gb > 0 else 0

        inbound = await self.get_inbound_by_id(inbound_id)
        protocol = inbound.get("protocol", "")

        client_entry = {
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_bytes,
            "expiryTime": expire_time,
            "enable": enable,
            "tgId": tg_id,
            "subId": uuid.uuid4().hex,
            "reset": 0,
        }

        if protocol == "trojan":
            client_entry["password"] = client_uuid
            client_entry["flow"] = flow
        else:
            client_entry["id"] = client_uuid
            client_entry["flow"] = flow

        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client_entry]}),
        }

        await self._request("POST", "/panel/api/inbounds/addClient", data=payload)

        return {
            "uuid": client_uuid,
            "email": email,
            "inbound_id": inbound_id,
            "expire_time": expire_time,
            "total_gb": total_gb,
        }

    def _parse_json_field(self, value, default=None):
        if default is None:
            default = {}

        if isinstance(value, dict):
            return value

        if not value:
            return default

        try:
            return json.loads(value)
        except Exception:
            return default

    async def get_inbound_by_id(self, inbound_id: int):
        inbounds = await self.get_inbounds()

        for inbound in inbounds:
            if inbound.get("id") == inbound_id:
                return inbound

        raise XUIError(f"Inbound с ID {inbound_id} не найден")

    async def get_client_by_email_or_uuid(
        self,
        inbound_id: int,
        email: str | None = None,
        client_uuid: str | None = None,
    ):
        inbound = await self.get_inbound_by_id(inbound_id)
        settings = self._parse_json_field(inbound.get("settings", "{}"), default={})
        clients = settings.get("clients", [])

        for client in clients:
            client_email = client.get("email")
            client_id = client.get("id")
            client_password = client.get("password")

            if email and client_email == email:
                return inbound, client

            if client_uuid and (client_id == client_uuid or client_password == client_uuid):
                return inbound, client

        raise XUIError("Клиент не найден в inbound")

    def _build_vless_uri(self, inbound: dict, client: dict, remark: str | None = None) -> str:
        stream = self._parse_json_field(inbound.get("streamSettings", "{}"), default={})

        host = self.host
        port = inbound.get("port")
        client_id = client.get("id")

        if not client_id:
            raise XUIError("У VLESS клиента нет id")

        network = stream.get("network", "tcp")
        security = stream.get("security", "none")

        params = {
            "type": network,
            "security": security,
        }

        if client.get("flow"):
            params["flow"] = client["flow"]

        if security == "reality":
            reality = stream.get("realitySettings", {}) or {}

            reality_settings = reality.get("settings", {}) or {}
            public_key = reality_settings.get("publicKey")
            fingerprint = reality_settings.get("fingerprint")
            spider_x = reality_settings.get("spiderX")

            short_ids = reality.get("shortIds", []) or []
            short_id = short_ids[0] if short_ids else ""

            server_names = reality.get("serverNames", []) or []
            server_name = server_names[0] if server_names else ""

            if server_name:
                params["sni"] = server_name
            if public_key:
                params["pbk"] = public_key
            if fingerprint:
                params["fp"] = fingerprint
            if short_id:
                params["sid"] = short_id
            if spider_x:
                params["spx"] = spider_x

        elif security == "tls":
            tls_settings = stream.get("tlsSettings", {}) or {}
            server_name = tls_settings.get("serverName")
            alpn = tls_settings.get("alpn")

            if server_name:
                params["sni"] = server_name
            if isinstance(alpn, list) and alpn:
                params["alpn"] = ",".join(alpn)

        if network == "ws":
            ws_settings = stream.get("wsSettings", {}) or {}
            path = ws_settings.get("path", "/")
            headers = ws_settings.get("headers", {}) or {}
            host_header = headers.get("Host")

            params["path"] = path or "/"
            if host_header:
                params["host"] = host_header

        elif network == "grpc":
            grpc_settings = stream.get("grpcSettings", {}) or {}
            service_name = grpc_settings.get("serviceName")
            if service_name:
                params["serviceName"] = service_name

        query_parts = []
        for key, value in params.items():
            if value is None or value == "":
                continue
            query_parts.append(f"{quote(str(key))}={quote(str(value))}")

        query = "&".join(query_parts)
        title = remark or inbound.get("remark") or "VPN"

        return f"vless://{client_id}@{host}:{port}?{query}#{quote(title)}"

    def _build_trojan_uri(self, inbound: dict, client: dict, remark: str | None = None) -> str:
        stream = self._parse_json_field(inbound.get("streamSettings", "{}"), default={})

        host = self.host
        port = inbound.get("port")
        password = client.get("password")

        if not password:
            raise XUIError("У Trojan клиента нет password")

        network = stream.get("network", "tcp")
        security = stream.get("security", "tls")

        params = {
            "type": network,
            "security": security,
        }

        if client.get("flow"):
            params["flow"] = client["flow"]

        if security == "tls":
            tls_settings = stream.get("tlsSettings", {}) or {}
            server_name = tls_settings.get("serverName")
            alpn = tls_settings.get("alpn")

            if server_name:
                params["sni"] = server_name
            if isinstance(alpn, list) and alpn:
                params["alpn"] = ",".join(alpn)

        if network == "ws":
            ws_settings = stream.get("wsSettings", {}) or {}
            path = ws_settings.get("path", "/")
            headers = ws_settings.get("headers", {}) or {}
            host_header = headers.get("Host")

            params["path"] = path or "/"
            if host_header:
                params["host"] = host_header

        elif network == "grpc":
            grpc_settings = stream.get("grpcSettings", {}) or {}
            service_name = grpc_settings.get("serviceName")
            if service_name:
                params["serviceName"] = service_name

        query_parts = []
        for key, value in params.items():
            if value is None or value == "":
                continue
            query_parts.append(f"{quote(str(key))}={quote(str(value))}")

        query = "&".join(query_parts)
        title = remark or inbound.get("remark") or "VPN"

        return f"trojan://{password}@{host}:{port}?{query}#{quote(title)}"

    async def build_connection_uri(
        self,
        inbound_id: int,
        email: str | None = None,
        client_uuid: str | None = None,
        remark: str | None = None,
        flow: str = "",
    ) -> str:
        inbound = await self.get_inbound_by_id(inbound_id)
        protocol = inbound.get("protocol", "")
        client = None

        try:
            _, client = await self.get_client_by_email_or_uuid(
                inbound_id=inbound_id,
                email=email,
                client_uuid=client_uuid,
            )
        except Exception:
            pass

        if client is None:
            if protocol == "vless":
                if not client_uuid:
                    raise XUIError("Нет UUID для VLESS клиента")

                client = {
                    "id": client_uuid,
                    "email": email,
                    "flow": flow,
                }

            elif protocol == "trojan":
                if not client_uuid:
                    raise XUIError("Нет password/UUID для Trojan клиента")

                client = {
                    "password": client_uuid,
                    "email": email,
                    "flow": flow,
                }
            else:
                raise XUIError(f"Неподдерживаемый протокол: {protocol}")

        if protocol == "vless":
            return self._build_vless_uri(inbound, client, remark=remark)

        if protocol == "trojan":
            return self._build_trojan_uri(inbound, client, remark=remark)

        raise XUIError(f"Неподдерживаемый протокол: {protocol}")
    
    
    async def delete_client(self, inbound_id: int, client_uuid: str):
        await self._request(
            "POST",
            f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}",
            data={},
        )

        return True
