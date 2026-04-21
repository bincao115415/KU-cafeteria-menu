import json as _json
import logging
from collections.abc import Callable
from datetime import date
from typing import Literal, TypedDict

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.models import TranslatedCafeteriaMenu, TranslatedWeeklyBundle
from src.photos import resolve_photo_url

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


# --- Summary page block builders ---

def _rt(text: str, *, italic: bool = False, bold: bool = False, link: str | None = None) -> dict:
    content = {"type": "text", "text": {"content": text}}
    if link:
        content["text"]["link"] = {"url": link}
    annotations: dict = {}
    if italic:
        annotations["italic"] = True
    if bold:
        annotations["bold"] = True
    if annotations:
        content["annotations"] = annotations
    return content


def _heading(level: int, text: str) -> dict:
    key = f"heading_{level}"
    return {"object": "block", "type": key, key: {"rich_text": [_rt(text)]}}


def _paragraph(spans: list[dict]) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": spans}}


def _callout(text: str, emoji: str = "🍱") -> dict:
    return {
        "object": "block", "type": "callout",
        "callout": {"rich_text": [_rt(text)], "icon": {"type": "emoji", "emoji": emoji}},
    }


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _bullet(spans: list[dict]) -> dict:
    return {
        "object": "block", "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": spans},
    }


def _toggle(text: str, children: list[dict]) -> dict:
    return {
        "object": "block", "type": "toggle",
        "toggle": {"rich_text": [_rt(text)], "children": children},
    }


def _day_toggle_children(categories: list[CategoryBlock]) -> list[dict]:
    blocks: list[dict] = []
    for blk in categories:
        blocks.append(_paragraph([_rt(f"【{blk['label_ko']}】", bold=True)]))
        for dish in blk["dishes"]:
            star = " ★" if dish["is_new"] else ""
            zh = dish["name_zh"] or dish["name_ko"]
            en = dish["name_en"]
            text = f"{zh}{star} / {en}" if en else f"{zh}{star}"
            blocks.append(_bullet([_rt(text)]))
    return blocks


_MEAL_EMOJI: dict[Meal, str] = {"午餐": "🍚", "晚餐": "🌙"}


def _summary_page_title(bundle: TranslatedWeeklyBundle) -> str:
    return f"{bundle.week_start.strftime('%Y/%m/%d')} 周菜单 · KU 食堂"


def _cafeteria_section(
    cm: TranslatedCafeteriaMenu, meals: list[MealRow]
) -> list[dict]:
    """Build blocks for one cafeteria: H2 + paragraph + (H3 + toggles per meal)."""
    blocks: list[dict] = []
    header = f"🏛 {cm.cafeteria_name_zh} · {cm.cafeteria_name_en}"
    blocks.append(_heading(2, header))

    if not meals:
        blocks.append(_paragraph([_rt("本周该食堂未提供数据", italic=True)]))
        return blocks

    blocks.append(_paragraph([
        _rt("📍 "),
        _rt("原始页面 →", link=cm.source_url),
    ]))

    by_meal: dict[Meal, list[MealRow]] = {"午餐": [], "晚餐": []}
    for m in meals:
        by_meal[m["meal"]].append(m)

    for meal in ("午餐", "晚餐"):
        if not by_meal[meal]:
            continue
        blocks.append(_heading(3, f"{_MEAL_EMOJI[meal]} {meal}"))
        for m in sorted(by_meal[meal], key=lambda x: x["date"]):
            toggle_title = f"{m['day']} · {m['date'].isoformat()}"
            blocks.append(_toggle(toggle_title, _day_toggle_children(m["categories"])))
    return blocks


def _summary_blocks(bundle: TranslatedWeeklyBundle, meals: list[MealRow]) -> list[dict]:
    blocks: list[dict] = []
    blocks.append(_heading(1, _summary_page_title(bundle)))
    blocks.append(_callout(
        f"本周新菜 {bundle.new_dish_count} 道 · {len(bundle.cafeterias)} 个食堂"
    ))
    blocks.append(_divider())

    meals_by_cafe: dict[str, list[MealRow]] = {}
    for m in meals:
        meals_by_cafe.setdefault(m["cafeteria_id"], []).append(m)

    for cm in bundle.cafeterias:
        blocks.extend(_cafeteria_section(cm, meals_by_cafe.get(cm.cafeteria_id, [])))

    blocks.append(_divider())
    blocks.append(_paragraph([_rt("翻译由 DeepSeek 两轮反思验证 · 每周一 10:30 KST 自动运行")]))
    return blocks


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

    async def build_summary_page(
        self,
        bundle: TranslatedWeeklyBundle,
        meals: list[MealRow],
    ) -> str:
        resp = await self._http("POST", "/pages", json={
            "parent": {"type": "page_id", "page_id": self.parent_page_id},
            "properties": {
                "title": {"title": [{"text": {"content": _summary_page_title(bundle)}}]},
            },
            "children": _summary_blocks(bundle, meals),
        })
        url = resp.get("url")
        if not url:
            raise RuntimeError(f"Notion /pages response missing url: {resp}")
        return url

    _FAILURE_THRESHOLD = 0.3

    def _photo_resolver(self) -> PhotoResolver:
        def resolver(cafeteria_id: str, name_ko: str, name_en: str) -> str | None:
            return resolve_photo_url(
                cafeteria_id, name_ko, name_en,
                unsplash_key=self._unsplash_key,
                repo_slug=self._repo_slug,
            )
        return resolver

    async def publish(self, bundle: TranslatedWeeklyBundle) -> PublishResult:
        meals = group_into_meals(bundle, self._photo_resolver())
        inserted = updated = failed = 0
        for meal in meals:
            status = await self.upsert_meal(meal)
            if status == "inserted":
                inserted += 1
            elif status == "updated":
                updated += 1
            else:
                failed += 1

        total = max(1, inserted + updated + failed)
        summary_url: str | None = None
        if failed / total > self._FAILURE_THRESHOLD:
            log.error(
                "meal upsert failure rate %.0f%% > %.0f%% → skipping summary page",
                failed / total * 100, self._FAILURE_THRESHOLD * 100,
            )
        else:
            try:
                summary_url = await self.build_summary_page(bundle, meals)
            except Exception:
                log.exception("summary page creation failed")

        return {
            "meals_inserted": inserted,
            "meals_updated": updated,
            "meals_failed": failed,
            "summary_page_url": summary_url,
        }

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
