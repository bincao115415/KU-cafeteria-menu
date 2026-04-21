import hashlib
import logging
from pathlib import Path

import httpx
from slugify import slugify

log = logging.getLogger(__name__)

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

_PHOTO_EXTS = ("jpg", "jpeg", "png", "webp")


def slugify_ko(name_ko: str) -> str:
    """Slug a Korean dish name. Falls back to sha1[:10] if transliteration yields empty."""
    s = slugify(name_ko, lowercase=True)
    if s:
        return s
    log.debug("slugify_ko fallback to sha1 for %r", name_ko)
    return hashlib.sha1(name_ko.encode("utf-8")).hexdigest()[:10]


def _search_unsplash(query: str, access_key: str) -> str | None:
    try:
        resp = httpx.get(
            "https://api.unsplash.com/search/photos",
            params={
                "query": query,
                "per_page": 1,
                "orientation": "landscape",
            },
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=10.0,
        )
    except httpx.HTTPError as e:
        log.warning("unsplash request failed: %s", e)
        return None
    if resp.status_code != 200:
        log.warning("unsplash %s: %s", resp.status_code, resp.text[:200])
        return None
    data = resp.json()
    results = data.get("results") or []
    if not results:
        return None
    return results[0].get("urls", {}).get("regular")


def resolve_photo_url(
    cafeteria_id: str,
    name_ko: str,
    name_en: str,
    *,
    data_dir: Path = DATA,
    unsplash_key: str | None = None,
    repo_slug: str = "bincao115415/KU-cafeteria-menu",
) -> str | None:
    """Return a photo URL for a dish: local file first, Unsplash fallback (stub), else None.

    Local convention: files live at `<data_dir>/photos/<cafeteria_id>/<slug>.<ext>`,
    slug = slugify_ko(name_ko). For real deployment `data_dir == <repo>/data`, so the
    public URL uses the `data/photos/...` path under the GitHub raw host.
    First match wins; extensions are checked in order: `jpg`, `jpeg`, `png`, `webp`.
    """
    slug = slugify_ko(name_ko)
    cafe_dir = data_dir / "photos" / cafeteria_id
    for ext in _PHOTO_EXTS:
        candidate = cafe_dir / f"{slug}.{ext}"
        if candidate.is_file():
            log.debug("local photo hit: %s/%s → .%s", cafeteria_id, name_ko, ext)
            return (
                f"https://raw.githubusercontent.com/{repo_slug}/main/"
                f"data/photos/{cafeteria_id}/{slug}.{ext}"
            )

    if unsplash_key:
        if not name_en or name_en.startswith("[translation failed]"):
            log.debug("skip unsplash: invalid name_en for %s", name_ko)
            return None
        query = f"{name_en} korean cafeteria food"
        hit = _search_unsplash(query, unsplash_key)
        if hit:
            return hit
        log.info("unsplash miss for %s (query=%r)", name_ko, query)
        return None
    log.debug(
        "no local photo for %s/%s (slug=%s); no unsplash key",
        cafeteria_id, name_ko, slug,
    )
    return None
