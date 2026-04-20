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
        choice = choices[0]
        message = choice.get("message") or choice.get("delta") or {}
        content = message.get("content")
        if content is None:
            log.warning("MiniMax choice missing content: %s", json.dumps(choice)[:800])
            return ""
        return content

    async def chat_json(self, user: str, *, system: str | None = None) -> dict:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        resp = await self._post_chat({
            "model": self.model,
            "messages": messages,
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
        parsed = _extract_first_json_object(raw)
        if parsed is None:
            log.warning("MiniMax returned non-JSON content: %r", raw[:200])
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_first_json_object(text: str) -> dict | None:
    """Find and parse the first balanced {...} object embedded in free text.

    Skips braces inside JSON strings. Returns None if no valid object parses.
    """
    depth = 0
    start = -1
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = -1
    return None
