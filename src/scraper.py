import asyncio
import logging

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=15),
    retry=retry_if_exception_type((httpx.HTTPError,)),
    reraise=True,
)
async def fetch_one(url: str, *, timeout: float = 30.0) -> str:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": _UA})
        r.raise_for_status()
        r.encoding = r.encoding or "utf-8"
        return r.text


async def fetch_all(
    cafeterias: list[dict],
) -> list[tuple[str, str | None, str | None]]:
    """Returns [(cafeteria_id, html_or_None, error_or_None), ...]."""

    async def one(c: dict) -> tuple[str, str | None, str | None]:
        try:
            html = await fetch_one(c["source_url"])
            return (c["cafeteria_id"], html, None)
        except Exception as e:
            log.warning("fetch failed for %s: %s", c["cafeteria_id"], e)
            return (c["cafeteria_id"], None, str(e))

    return await asyncio.gather(*[one(c) for c in cafeterias])
