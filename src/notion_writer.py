import json as _json
import logging
from datetime import date
from typing import Callable, Literal, TypedDict

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.models import TranslatedWeeklyBundle

log = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

Meal = Literal["午餐", "晚餐"]
DayCode = Literal["Mon", "Tue", "Wed", "Thu", "Fri"]
Confidence = Literal["high", "medium", "low", "failed"]

WEEKDAY_CODE: dict[str, DayCode] = {
    "MON": "Mon", "TUE": "Tue", "WED": "Wed", "THU": "Thu", "FRI": "Fri",
}

CAFETERIA_SHORT_ZH: dict[str, str] = {
    "science": "科学",
    "anam": "安岩",
    "sanhak": "产学",
    "alumni": "校友",
    "student_center": "学生中心",
}

_HIDDEN_CATEGORIES = {"조식", "천원의아침", "천원의아침(테이크아웃)", "아침"}
_CONF_ORDER: dict[Confidence, int] = {"high": 0, "medium": 1, "low": 2, "failed": 3}

PhotoResolver = Callable[[str, str, str], str | None]


class DishLine(TypedDict):
    name_ko: str
    name_zh: str
    name_en: str
    is_new: bool
    photo_url: str | None


class CategoryBlock(TypedDict):
    label_ko: str
    dishes: list[DishLine]


class MealRow(TypedDict):
    week_monday: date
    day: DayCode
    date: date
    cafeteria_id: str
    cafeteria_name_zh_full: str
    cafeteria_name_en_full: str
    meal: Meal
    categories: list[CategoryBlock]
    dish_count: int
    new_count: int
    confidence: Confidence
    source_url: str


class PublishResult(TypedDict):
    meals_inserted: int
    meals_updated: int
    meals_failed: int
    summary_page_url: str | None


def classify_meal(category_ko: str) -> Meal:
    return "晚餐" if "석식" in category_ko else "午餐"


def _worst_confidence(confidences: list[Confidence]) -> Confidence:
    if not confidences:
        return "high"
    return max(confidences, key=lambda c: _CONF_ORDER[c])


def group_into_meals(
    bundle: TranslatedWeeklyBundle,
    resolve_photo: PhotoResolver,
) -> list[MealRow]:
    meals: list[MealRow] = []
    for cm in bundle.cafeterias:
        for d in cm.days:
            if d.weekday not in WEEKDAY_CODE:
                continue
            by_meal: dict[Meal, dict[str, list[DishLine]]] = {"午餐": {}, "晚餐": {}}
            conf_by_meal: dict[Meal, list[Confidence]] = {"午餐": [], "晚餐": []}

            for cat_ko, dishes in d.categories.items():
                if cat_ko in _HIDDEN_CATEGORIES or not dishes:
                    continue
                meal = classify_meal(cat_ko)
                bucket = by_meal[meal].setdefault(cat_ko, [])
                for dish in dishes:
                    bucket.append({
                        "name_ko": dish.name_ko,
                        "name_zh": dish.name_zh,
                        "name_en": dish.name_en,
                        "is_new": dish.is_new,
                        "photo_url": resolve_photo(cm.cafeteria_id, dish.name_ko, dish.name_en),
                    })
                    conf_by_meal[meal].append(dish.confidence)

            for meal in ("午餐", "晚餐"):
                if not by_meal[meal]:
                    continue
                cats: list[CategoryBlock] = [
                    {"label_ko": label, "dishes": lines}
                    for label, lines in by_meal[meal].items()
                ]
                all_lines = [ln for blk in cats for ln in blk["dishes"]]
                meals.append({
                    "week_monday": bundle.week_start,
                    "day": WEEKDAY_CODE[d.weekday],
                    "date": d.date,
                    "cafeteria_id": cm.cafeteria_id,
                    "cafeteria_name_zh_full": cm.cafeteria_name_zh,
                    "cafeteria_name_en_full": cm.cafeteria_name_en,
                    "meal": meal,
                    "categories": cats,
                    "dish_count": len(all_lines),
                    "new_count": sum(1 for ln in all_lines if ln["is_new"]),
                    "confidence": _worst_confidence(conf_by_meal[meal]),
                    "source_url": cm.source_url,
                })
    return meals


# --- HTTP plumbing (used by Tasks 5-7) ---

class _Retryable(Exception):
    """Raised on 429/5xx to trigger tenacity backoff."""


_DISHES_SOFT_LIMIT = 2000  # Notion rich_text content limit


def _render_dishes_text(categories: list[CategoryBlock]) -> str:
    lines: list[str] = []
    for blk in categories:
        lines.append(f"【{blk['label_ko']}】")
        for dish in blk["dishes"]:
            star = " ★" if dish["is_new"] else ""
            zh = dish["name_zh"] or dish["name_ko"]
            en = dish["name_en"] or ""
            lines.append(f"• {zh}{star} / {en}".rstrip(" /"))
        lines.append("")
    text = "\n".join(lines).rstrip()
    if len(text) <= _DISHES_SOFT_LIMIT:
        return text
    truncated = text[: _DISHES_SOFT_LIMIT - 24].rstrip()
    dropped = text[len(truncated):].count("\n•")
    return f"{truncated}\n… (+{dropped} more)"


def _meal_properties(meal: MealRow) -> dict:
    title = (
        f"{meal['date'].isoformat()} {meal['day']} · "
        f"{CAFETERIA_SHORT_ZH[meal['cafeteria_id']]} · {meal['meal']}"
    )
    photo_urls: list[str] = [
        ln["photo_url"]
        for blk in meal["categories"] for ln in blk["dishes"]
        if ln["photo_url"]
    ]
    return {
        "Name": {"title": [{"text": {"content": title}}]},
        "Week": {"date": {"start": meal["week_monday"].isoformat()}},
        "Day": {"select": {"name": meal["day"]}},
        "Cafeteria": {"select": {"name": CAFETERIA_SHORT_ZH[meal["cafeteria_id"]]}},
        "Meal": {"select": {"name": meal["meal"]}},
        "Photo": {"files": [
            {
                "type": "external",
                "name": (url.rsplit("/", 1)[-1] or "photo")[:100],
                "external": {"url": url},
            }
            for url in photo_urls[:25]  # Notion limit: 25 files per property
        ]},
        "Dishes": {"rich_text": [{"text": {"content": _render_dishes_text(meal["categories"])}}]},
        "Dish Count": {"number": meal["dish_count"]},
        "New Count": {"number": meal["new_count"]},
        "Confidence": {"select": {"name": meal["confidence"]}},
        "Source URL": {"url": meal["source_url"]},
    }


class NotionWriter:
    def __init__(
        self,
        *,
        token: str,
        database_id: str,
        parent_page_id: str,
        repo_slug: str = "bincao115415/KU-cafeteria-menu",
        unsplash_key: str | None = None,
    ):
        self._token = token
        self.database_id = database_id
        self.parent_page_id = parent_page_id
        self._repo_slug = repo_slug
        self._unsplash_key = unsplash_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "NotionWriter":
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(min=1, max=30),
        retry=retry_if_exception_type(_Retryable),
        reraise=True,
    )
    async def _http(self, method: str, path: str, *, json: dict | None = None) -> dict:
        if self._client is None:
            raise RuntimeError("use `async with NotionWriter(...)`")
        content = (
            _json.dumps(json, ensure_ascii=False).encode("utf-8")
            if json is not None else None
        )
        resp = await self._client.request(
            method, f"{NOTION_API}{path}", content=content,
        )
        if resp.status_code == 429:
            # Tenacity's wait_exponential (1-30s) owns backoff; Retry-After is
            # logged for observability only to avoid compounding the wait.
            retry_after = resp.headers.get("Retry-After")
            log.warning("notion 429 on %s %s (Retry-After=%s)", method, path, retry_after)
            raise _Retryable(f"{method} {path}: 429")
        if 500 <= resp.status_code < 600:
            raise _Retryable(f"{method} {path}: {resp.status_code}")
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Notion {method} {path} → {resp.status_code}: {resp.text[:400]}"
            )
        return resp.json()

    async def _find_existing(self, meal: MealRow) -> str | None:
        body = {
            "filter": {"and": [
                {"property": "Week", "date": {"equals": meal["week_monday"].isoformat()}},
                {"property": "Day", "select": {"equals": meal["day"]}},
                {"property": "Cafeteria",
                 "select": {"equals": CAFETERIA_SHORT_ZH[meal["cafeteria_id"]]}},
                {"property": "Meal", "select": {"equals": meal["meal"]}},
            ]},
            "page_size": 1,
        }
        resp = await self._http(
            "POST", f"/databases/{self.database_id}/query", json=body
        )
        results = resp.get("results") or []
        return results[0]["id"] if results else None

    async def upsert_meal(self, meal: MealRow) -> Literal["inserted", "updated", "failed"]:
        try:
            existing_id = await self._find_existing(meal)
            props = _meal_properties(meal)
            if existing_id:
                await self._http(
                    "PATCH", f"/pages/{existing_id}", json={"properties": props}
                )
                return "updated"
            await self._http("POST", "/pages", json={
                "parent": {"database_id": self.database_id},
                "properties": props,
            })
            return "inserted"
        except Exception:
            log.exception(
                "upsert failed: %s %s %s %s",
                meal["cafeteria_id"], meal["day"], meal["meal"], meal["week_monday"],
            )
            return "failed"
