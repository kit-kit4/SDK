from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Optional, Sequence, Union

import httpx

from .config import Config
from .exceptions import UBNError, UBNAuthError, UBNRateLimitError
from .limiter import AsyncTokenBucketLimiter
from .queue import AsyncFileQueue
from .schema import infer_schema, schema_hash

class AsyncUBN:
    def __init__(
        self,
        token: Optional[str] = None,
        public_id: Optional[str] = None,
        base_url: Optional[str] = None,
        queue_path: Optional[Union[str, Path]] = ".ubn_queue.jsonl",
        timeout: float = 30.0,
        max_batch_size: int = 50,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.config = Config()
        self.config.load()
        self.token = token or self.config.token
        self.public_id = public_id or self.config.public_id
        self.base_url = (base_url or self.config.base_url).rstrip("/")
        self.timeout = timeout
        self.max_batch_size = max_batch_size
        self.queue = AsyncFileQueue(queue_path) if queue_path else None
        self.limiter = AsyncTokenBucketLimiter(rate_per_minute=60, burst=60)
        self._client = http_client or httpx.AsyncClient(timeout=timeout)
        self._owned = http_client is None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._owned:
            await self._client.aclose()

    # ---------- Реєстрація ----------
    async def register(
        self,
        name: str,
        app_type: str = "telegram",
        default_level: int = 1,
        bot_username: Optional[str] = None,
        owner_telegram_id: Optional[str] = None,
        features: Optional[list[str]] = None,
        save_config: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "name": name,
            "type": app_type,
            "defaultLevel": default_level,
            "botUsername": bot_username,
            "ownerTelegramId": owner_telegram_id,
            "features": features or ["presence", "storage", "schema", "webhook", "grants"],
        }
        data = await self._request("POST", "/net/bots/register", payload, auth=False)
        if not data.get("ok"):
            raise UBNError(f"Registration failed: {data}")
        self.token = data["apiKey"]
        self.public_id = data["publicId"]
        if save_config:
            self.config.token = self.token
            self.config.public_id = self.public_id
            self.config.base_url = self.base_url
            self.config.save()
        return data

    # ---------- Presence ----------
    async def publish_presence(
        self,
        chats: Sequence[dict[str, Any]],
        auto_batch: bool = True,
    ) -> list[dict[str, Any]]:
        if not chats:
            return []
        if auto_batch:
            batches = [chats[i:i+self.max_batch_size] for i in range(0, len(chats), self.max_batch_size)]
        else:
            batches = [chats]
        results = []
        for batch in batches:
            payload = {"chats": batch}
            await self.limiter.acquire()
            resp = await self._request("PUT", "/net/presence/batch", payload, auth=True)
            results.append(resp)
        return results

    async def get_presence(self, chat_ids: Sequence[str]) -> dict[str, Any]:
        if not chat_ids:
            return {"chats": {}, "skipped": {}}
        results = {"chats": {}, "skipped": {"chatIds": [], "reason": ""}}
        for i in range(0, len(chat_ids), 50):
            batch = chat_ids[i:i+50]
            query = "chatIds=" + ",".join(batch)
            await self.limiter.acquire()
            resp = await self._request("GET", f"/net/presence/batch?{query}", auth=True)
            if resp.get("chats"):
                results["chats"].update(resp["chats"])
            if resp.get("skipped"):
                results["skipped"]["chatIds"].extend(resp["skipped"].get("chatIds", []))
        return results

    # ---------- Grants ----------
    async def create_grant(self, grantee_public_id: str, level: int) -> dict[str, Any]:
        payload = {"granteePublicId": grantee_public_id, "level": level}
        await self.limiter.acquire()
        return await self._request("POST", "/net/grants", payload, auth=True)

    async def revoke_grant(self, grantee_public_id: str) -> dict[str, Any]:
        await self.limiter.acquire()
        return await self._request("DELETE", f"/net/grants/{grantee_public_id}", auth=True)

    async def list_grants(self) -> list[dict[str, Any]]:
        await self.limiter.acquire()
        resp = await self._request("GET", "/net/grants", auth=True)
        return resp.get("grants", [])

    # ---------- Webhooks ----------
    async def create_webhook(self, url: str, events: list[str]) -> dict[str, Any]:
        payload = {"url": url, "events": events}
        await self.limiter.acquire()
        return await self._request("POST", "/net/webhooks", payload, auth=True)

    async def list_webhooks(self) -> list[dict[str, Any]]:
        await self.limiter.acquire()
        resp = await self._request("GET", "/net/webhooks", auth=True)
        return resp.get("webhooks", [])

    async def delete_webhook(self, webhook_id: str) -> dict[str, Any]:
        await self.limiter.acquire()
        return await self._request("DELETE", f"/net/webhooks/{webhook_id}", auth=True)

    # ---------- Schemas ----------
    async def publish_schema(self, capability: str, schema_version: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "capability": capability,
            "schemaVersion": schema_version,
            "schema": schema,
        }
        await self.limiter.acquire()
        return await self._request("PUT", "/net/schemas", payload, auth=True)

    async def get_schema(self, public_id: str, capability: str) -> Optional[dict[str, Any]]:
        resp = await self._request("GET", f"/net/schemas/{public_id}/{capability}", auth=False)
        return resp.get("schema")

    async def list_schemas(self, public_id: str) -> list[dict[str, Any]]:
        resp = await self._request("GET", f"/net/schemas/{public_id}", auth=False)
        return resp.get("schemas", [])

    # ---------- Profile ----------
    async def update_profile(self, bio: Optional[str] = None, capabilities: Optional[list[str]] = None, features: Optional[list[str]] = None) -> dict[str, Any]:
        payload = {}
        if bio is not None:
            payload["bio"] = bio
        if capabilities is not None:
            payload["capabilities"] = capabilities
        if features is not None:
            payload["features"] = features
        await self.limiter.acquire()
        return await self._request("PATCH", "/net/bots/me", payload, auth=True)

    async def get_public_profile(self, public_id: str) -> dict[str, Any]:
        resp = await self._request("GET", f"/net/bots/{public_id}", auth=False)
        return resp.get("bot", {})

    async def get_my_profile(self) -> dict[str, Any]:
        # немає прямого ендпоінта, але можна використати get_public_profile зі своїм public_id
        return await self.get_public_profile(self.public_id)

    async def discover_bots(self, capability: Optional[str] = None, bot_type: Optional[str] = None, feature: Optional[str] = None, features: Optional[str] = None) -> list[dict[str, Any]]:
        params = []
        if capability:
            params.append(f"capability={capability}")
        if bot_type:
            params.append(f"type={bot_type}")
        if feature:
            params.append(f"feature={feature}")
        if features:
            params.append(f"features={features}")
        query = "&".join(params)
        resp = await self._request("GET", f"/net/bots/discover?{query}", auth=False)
        return resp.get("bots", [])

    async def rotate_key(self) -> dict[str, Any]:
        await self.limiter.acquire()
        resp = await self._request("POST", "/net/bots/rotate-key", auth=True)
        if resp.get("ok"):
            self.token = resp["apiKey"]
            self.config.token = self.token
            self.config.save()
        return resp

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/net/health", auth=False)

    # ---------- Queue ----------
    async def flush_queued(self, silent: bool = False) -> int:
        if not self.queue:
            return 0
        items = await self.queue.pop_all()
        if not items:
            return 0
        sent = 0
        for item in items:
            try:
                await self.limiter.acquire()
                await self._request("PUT", "/net/presence/batch", item, auth=True)
                sent += 1
            except Exception:
                await self.queue.push(item)
                if not silent:
                    break
                break
        return sent

    # ---------- HTTP ----------
    async def _request(
        self,
        method: str,
        path: str,
        payload: Optional[dict[str, Any]] = None,
        auth: bool = True,
    ) -> dict[str, Any]:
        url = self.base_url + path
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ubn-sdk/0.3.0",
        }
        if auth:
            if not self.token:
                raise UBNError("Missing UBN token. Run 'ubn init' first.")
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            resp = await self._client.request(
                method=method,
                url=url,
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok", True):
                error = data.get("error", "Unknown error")
                if "retryAfterSec" in data:
                    raise UBNRateLimitError(f"Rate limit: {error}")
                raise UBNError(f"API error: {error}")
            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise UBNAuthError("Invalid or missing token")
            if e.response.status_code == 429:
                retry_after = e.response.json().get("retryAfterSec", 1)
                raise UBNRateLimitError(f"Rate limited, retry after {retry_after}s")
            raise UBNError(f"HTTP {e.response.status_code}: {e.response.text}")
        except httpx.TimeoutException:
            raise UBNError("Request timeout")