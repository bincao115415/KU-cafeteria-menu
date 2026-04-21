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
    """Returns [(cafeteria_id, html_or_None, error_or_None), ...].

    URLs are deduped: each unique source_url is fetched exactly once, then the
    html (or error) is fanned out to every cafeteria entry pointing to it.
    """

    unique_urls = list({c["source_url"] for c in cafeterias})

    async def one(url: str) -> tuple[str, str | None, str | None]:
        try:
            html = await fetch_one(url)
            return (url, html, None)
        except Exception as e:
            log.warning("fetch failed for %s: %s", url, e)
            return (url, None, str(e))

    results = await asyncio.gather(*[one(u) for u in unique_urls])
    by_url = {url: (html, err) for url, html, err in results}
    return [
        (c["cafeteria_id"], by_url[c["source_url"]][0], by_url[c["source_url"]][1])
        for c in cafeterias
    ]
