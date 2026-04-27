import asyncio
import aiohttp
import json
import logging
import time
import uuid
from urllib.parse import quote, urlparse

from config import PANEL_LOGIN, PANEL_PASSWORD, PANEL_PATH, PANEL_URL


logger = logging.getLogger(__name__)


class XUIError(Exception):
    pass


def _build_panel_base_url() -> str:
    if not PANEL_URL:
        raise XUIError("PANEL_URL не настроен")

    parsed_url = urlparse(PANEL_URL)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        raise XUIError("PANEL_URL должен содержать http(s)://host:port")

    base_url = PANEL_URL.rstrip("/")
    panel_path = (PANEL_PATH or "").strip()
    if panel_path and not panel_path.startswith("/"):
        panel_path = f"/{panel_path}"

    return f"{base_url}{panel_path.rstrip('/')}"


class XUIClient:
    def __init__(self, server: dict):
        self.server = server
        self.host = server["host"]
        self.port = server["port"]
        self.protocol = server.get("protocol", "https")

        self.base_url = _build_panel_base_url()
        self.panel_login = PANEL_LOGIN or server["login"]
        self.panel_password = PANEL_PASSWORD or server["password"]
        self.session = None
        self.is_authenticated = False
        self._inbounds_cache = None

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector()
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

    def _invalidate_auth(self):
        self.is_authenticated = False
        self._inbounds_cache = None
        if self.session and not self.session.closed:
            self.session.cookie_jar.clear()

    @staticmethod
    def _looks_like_html_response(text: str) -> bool:
        stripped = text.lstrip().lower()
        return stripped.startswith("<!doctype html") or stripped.startswith("<html")

    @staticmethod
    def _is_auth_error_message(message: str | None) -> bool:
        if not message:
            return False

        normalized = str(message).strip().lower()
        auth_markers = (
            "login",
            "not login",
            "session",
            "unauthorized",
            "forbidden",
            "expired",
        )
        return any(marker in normalized for marker in auth_markers)

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def login(self):
        session = await self._ensure_session()

        data = {
            "username": self.panel_login,
            "password": self.panel_password,
        }

        login_url = f"{self.base_url}/login"

        try:
            async with session.post(login_url, data=data) as response:
                text = await response.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            logger.exception(
                "Failed to connect to XUI panel during login: host=%s port=%s",
                self.host,
                self.port,
            )
            raise XUIError("Не удалось подключиться к панели 3x-ui") from error

        if response.status != 200:
            logger.error(
                "XUI login failed with HTTP status: host=%s port=%s status=%s",
                self.host,
                self.port,
                response.status,
            )
            raise XUIError(f"Ошибка логина: HTTP {response.status}")

        try:
            result = json.loads(text)
        except json.JSONDecodeError as error:
            logger.error(
                "XUI login returned non-JSON response: host=%s port=%s",
                self.host,
                self.port,
            )
            raise XUIError("Панель вернула не JSON при логине") from error

        if result.get("success") is False:
            message = result.get("msg", "Не удалось войти в панель")
            logger.error(
                "XUI login was rejected: host=%s port=%s message=%s",
                self.host,
                self.port,
                message,
            )
            raise XUIError(message)

        self.is_authenticated = True
        return True

    async def _request(self, method: str, endpoint: str, data: dict | None = None):
        session = await self._ensure_session()

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }

        for attempt in range(2):
            if not self.is_authenticated and endpoint != "/login":
                await self.login()

            try:
                async with session.request(method, url, json=data, headers=headers) as response:
                    text = await response.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                logger.exception(
                    "XUI request failed because of network error: method=%s endpoint=%s host=%s port=%s",
                    method,
                    endpoint,
                    self.host,
                    self.port,
                )
                raise XUIError("Не удалось выполнить запрос к панели 3x-ui") from error

            if response.status in (401, 403) and endpoint != "/login" and attempt == 0:
                logger.warning(
                    "XUI session looks expired, retrying login: method=%s endpoint=%s status=%s",
                    method,
                    endpoint,
                    response.status,
                )
                self._invalidate_auth()
                continue

            if response.status != 200:
                logger.error(
                    "XUI request failed with HTTP status: method=%s endpoint=%s status=%s",
                    method,
                    endpoint,
                    response.status,
                )
                raise XUIError(f"HTTP {response.status}: {text[:200]}")

            try:
                result = json.loads(text)
            except json.JSONDecodeError as error:
                if endpoint != "/login" and attempt == 0 and self._looks_like_html_response(text):
                    logger.warning(
                        "XUI returned HTML instead of JSON, retrying login: method=%s endpoint=%s",
                        method,
                        endpoint,
                    )
                    self._invalidate_auth()
                    continue
                raise XUIError("Панель вернула не JSON") from error

            if result.get("success") is False:
                message = result.get("msg", "Ошибка запроса к панели")
                if endpoint != "/login" and attempt == 0 and self._is_auth_error_message(message):
                    logger.warning(
                        "XUI request was rejected because of auth state, retrying login: method=%s endpoint=%s message=%s",
                        method,
                        endpoint,
                        message,
                    )
                    self._invalidate_auth()
                    continue
                logger.error(
                    "XUI request was rejected: method=%s endpoint=%s message=%s",
                    method,
                    endpoint,
                    message,
                )
                raise XUIError(message)

            return result

        raise XUIError("Не удалось выполнить запрос к панели после повторного входа")

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

        try:
            inbound = await self.get_inbound_by_id(inbound_id)
            protocol = inbound.get("protocol", "")
        except Exception:
            logger.exception("Failed to prepare XUI client creation: inbound_id=%s email=%s", inbound_id, email)
            raise

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

        try:
            await self._request("POST", "/panel/api/inbounds/addClient", data=payload)
            self._inbounds_cache = None
            await self.get_client_by_email_or_uuid(
                inbound_id=inbound_id,
                email=email,
                client_uuid=client_uuid,
            )
        except Exception:
            logger.exception(
                "Failed to add XUI client: inbound_id=%s email=%s client_uuid_prefix=%s",
                inbound_id,
                email,
                client_uuid[:8],
            )
            raise

        logger.info(
            "Added XUI client: inbound_id=%s email=%s client_uuid_prefix=%s",
            inbound_id,
            email,
            client_uuid[:8],
        )

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
        try:
            target_id = int(inbound_id)
        except (TypeError, ValueError):
            logger.error("Invalid inbound_id value: %r", inbound_id)
            raise XUIError("inbound_id должен быть числом")

        inbounds = await self.get_inbounds()

        for inbound in inbounds:
            try:
                current_id = int(inbound.get("id"))
            except (TypeError, ValueError):
                continue

            if current_id == target_id:
                return inbound

        available_ids = [
            inbound.get("id")
            for inbound in inbounds
            if inbound.get("id") is not None
        ]
        logger.error(
            "Inbound was not found in 3x-ui: requested_id=%s available_ids=%s",
            target_id,
            available_ids,
        )
        raise XUIError(f"Inbound с ID {target_id} не найден")

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
        _, client = await self.get_client_by_email_or_uuid(
            inbound_id=inbound_id,
            email=email,
            client_uuid=client_uuid,
        )

        if protocol == "vless":
            return self._build_vless_uri(inbound, client, remark=remark)

        if protocol == "trojan":
            return self._build_trojan_uri(inbound, client, remark=remark)

        raise XUIError(f"Неподдерживаемый протокол: {protocol}")
    
    async def update_client_expiry(
        self,
        inbound_id: int,
        client_uuid: str,
        expire_time: int,
        email: str | None = None,
    ):
        try:
            _, client = await self.get_client_by_email_or_uuid(
                inbound_id=inbound_id,
                email=email,
                client_uuid=client_uuid,
            )
        except Exception:
            logger.exception(
                "Failed to find XUI client before expiry update: inbound_id=%s email=%s client_uuid_prefix=%s",
                inbound_id,
                email,
                client_uuid[:8],
            )
            raise

        updated_client = dict(client)
        updated_client["expiryTime"] = expire_time

        client_identifier = (
            updated_client.get("id")
            or updated_client.get("password")
            or client_uuid
        )
        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [updated_client]}),
        }

        try:
            await self._request(
                "POST",
                f"/panel/api/inbounds/updateClient/{client_identifier}",
                data=payload,
            )
            self._inbounds_cache = None
        except Exception:
            logger.exception(
                "Failed to update XUI client expiry: inbound_id=%s email=%s client_uuid_prefix=%s",
                inbound_id,
                email,
                client_uuid[:8],
            )
            raise

        _, refreshed_client = await self.get_client_by_email_or_uuid(
            inbound_id=inbound_id,
            email=email,
            client_uuid=client_uuid,
        )
        refreshed_expiry = int(refreshed_client.get("expiryTime") or 0)
        if refreshed_expiry != expire_time:
            raise XUIError("Панель не подтвердила новый срок клиента")

        logger.info(
            "Updated XUI client expiry: inbound_id=%s email=%s client_uuid_prefix=%s expire_time=%s",
            inbound_id,
            email,
            client_uuid[:8],
            expire_time,
        )
        return True
    
    
    async def delete_client(self, inbound_id: int, client_uuid: str):
        try:
            await self._request(
                "POST",
                f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}",
                data={},
            )
            self._inbounds_cache = None
        except Exception:
            logger.exception(
                "Failed to delete XUI client: inbound_id=%s client_uuid_prefix=%s",
                inbound_id,
                client_uuid[:8],
            )
            raise

        try:
            await self.get_client_by_email_or_uuid(
                inbound_id=inbound_id,
                client_uuid=client_uuid,
            )
        except XUIError as error:
            if str(error) == "Клиент не найден в inbound":
                logger.info(
                    "Deleted XUI client: inbound_id=%s client_uuid_prefix=%s",
                    inbound_id,
                    client_uuid[:8],
                )
                return True
            logger.exception(
                "Failed to verify XUI client deletion: inbound_id=%s client_uuid_prefix=%s",
                inbound_id,
                client_uuid[:8],
            )
            raise

        logger.error(
            "XUI client is still present after deletion: inbound_id=%s client_uuid_prefix=%s",
            inbound_id,
            client_uuid[:8],
        )
        raise XUIError("Панель не подтвердила удаление клиента")
