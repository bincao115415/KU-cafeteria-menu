import json
import logging

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.minimaxi.com/v1/text/chatcompletion_v2"
_DEFAULT_MODEL = "MiniMax-Text-01"


class MiniMaxClient:
    def __init__(
        self,
        api_key: str,
        group_id: str,
        model: str = _DEFAULT_MODEL,
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.group_id = group_id
        self.model = model
        self.timeout = timeout

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        retry=retry_if_exception_type((httpx.HTTPError,)),
        reraise=True,
    )
    async def _post_chat(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                _ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )
            r.raise_for_status()
            return r.json()

    @staticmethod
    def _extract_content(resp: dict) -> str:
        base = resp.get("base_resp")
        if isinstance(base, dict) and base.get("status_code", 0) not in (0, None):
            raise RuntimeError(
                f"MiniMax error {base.get('status_code')}: {base.get('status_msg')}"
            )
        choices = resp.get("choices")
        if not choices:
            log.warning("MiniMax response missing choices: %s", json.dumps(resp)[:800])
            raise KeyError("choices")
        return choices[0]["message"]["content"]

    async def chat_json(self, user: str, *, system: str | None = None) -> dict:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        resp = await self._post_chat({
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        })
        return _safe_json(self._extract_content(resp))

    async def chat_with_web_search(self, user: str, *, system: str | None = None) -> dict:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        resp = await self._post_chat({
            "model": self.model,
            "messages": messages,
            "tools": [{"type": "web_search"}],
            "tool_choice": "auto",
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        })
        return _safe_json(self._extract_content(resp))


def _safe_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("MiniMax returned non-JSON content: %r", raw[:200])
        return {}
    return parsed if isinstance(parsed, dict) else {}
