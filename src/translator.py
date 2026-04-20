import asyncio
import logging
from datetime import date
from typing import Protocol

from src.cache import TranslationCache
from src.models import (
    CafeteriaMenu,
    DishRaw,
    DishTranslated,
    TranslatedCafeteriaMenu,
    TranslatedDaySection,
)
from src.utils import normalize_dish_name

log = logging.getLogger(__name__)

_SYSTEM_PASS1 = """你是韩国餐饮翻译专家。给出一个韩国料理菜名的中文名、英文名,以及一句成分/做法说明。
- 中文名优先使用中国大陆常见译法(例如 된장찌개 → 大酱汤, 而不是字面直译)。
- 英文名使用餐饮业常见英文说法(例如 Soybean Paste Stew)。
- note_zh 和 note_en 是可选的一句话成分说明, <=30 字/单词。
严格只输出 JSON:{"zh": "...", "en": "...", "note_zh": "... or null", "note_en": "... or null"}。"""

_SYSTEM_PASS2 = """你在审阅另一个 LLM 对韩国料理菜名的翻译。
你可以使用 web_search 工具查询这道菜的常用中文/英文译法。
给出裁定:
- "confirm" 如果原译已经是常用/惯用说法;
- "revise" 如果搜索到更通用的译法(在 revised 字段里给出新的 zh/en/note_zh/note_en);
- "no_signal" 如果搜索无法给出有效信号。
严格只输出 JSON:{"verdict": "confirm"|"revise"|"no_signal", "revised": {...}}。revised 仅在 verdict==revise 时需要。"""


class ChatClient(Protocol):
    async def chat_json(self, user: str, *, system: str | None = None) -> dict: ...
    async def chat_with_web_search(self, user: str, *, system: str | None = None) -> dict: ...


def _norm_note(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


class Translator:
    def __init__(
        self,
        client: ChatClient,
        cache: TranslationCache,
        *,
        concurrency: int = 5,
    ):
        self.client = client
        self.cache = cache
        self._sem = asyncio.Semaphore(concurrency)

    async def translate_menu(self, menu: CafeteriaMenu) -> TranslatedCafeteriaMenu:
        errors: list[str] = []

        unique_keys: dict[str, DishRaw] = {}
        for day in menu.days:
            for cat_dishes in day.categories.values():
                for d in cat_dishes:
                    try:
                        k = normalize_dish_name(d.name_ko)
                    except ValueError:
                        continue
                    unique_keys.setdefault(k, d)

        async def resolve(key: str, raw: DishRaw) -> tuple[str, DishTranslated]:
            async with self._sem:
                hit = self.cache.get(key)
                if hit is not None:
                    return key, DishTranslated(
                        name_ko=raw.name_ko,
                        name_zh=hit["zh"],
                        name_en=hit["en"],
                        note_zh=hit.get("note_zh"),
                        note_en=hit.get("note_en"),
                        is_new=False,
                        confidence=hit.get("confidence", "high"),
                    )
                try:
                    p1 = await self.client.chat_json(
                        f"菜名:{raw.name_ko}", system=_SYSTEM_PASS1,
                    )
                    p2 = await self.client.chat_with_web_search(
                        f"菜名韩文:{raw.name_ko}\n初版翻译:{p1}",
                        system=_SYSTEM_PASS2,
                    )
                    verdict = p2.get("verdict", "no_signal")
                    if verdict == "confirm":
                        chosen, confidence, searched = p1, "high", True
                    elif verdict == "revise":
                        chosen, confidence, searched = p2.get("revised") or p1, "medium", True
                    else:
                        chosen, confidence, searched = p1, "low", False

                    entry = {
                        "zh": chosen["zh"],
                        "en": chosen["en"],
                        "note_zh": _norm_note(chosen.get("note_zh")),
                        "note_en": _norm_note(chosen.get("note_en")),
                        "learned_at": date.today().isoformat(),
                        "source": "minimax-two-pass",
                        "search_confirmed": searched,
                        "confidence": confidence,
                    }
                    self.cache.set(key, entry)
                    return key, DishTranslated(
                        name_ko=raw.name_ko,
                        name_zh=entry["zh"],
                        name_en=entry["en"],
                        note_zh=entry["note_zh"],
                        note_en=entry["note_en"],
                        is_new=True,
                        confidence=confidence,
                    )
                except Exception as e:
                    log.warning("translate failed for %s: %s", raw.name_ko, e)
                    errors.append(f"{raw.name_ko}: {e}")
                    return key, DishTranslated(
                        name_ko=raw.name_ko,
                        name_zh="[translation failed]",
                        name_en="[translation failed]",
                        is_new=True,
                        confidence="failed",
                    )

        results = await asyncio.gather(*[resolve(k, d) for k, d in unique_keys.items()])
        resolved_by_key = {k: dt for k, dt in results}

        new_days: list[TranslatedDaySection] = []
        for day in menu.days:
            tcat: dict[str, list[DishTranslated]] = {}
            for cat, ds in day.categories.items():
                tcat[cat] = []
                for d in ds:
                    try:
                        k = normalize_dish_name(d.name_ko)
                    except ValueError:
                        continue
                    tcat[cat].append(resolved_by_key[k])
            new_days.append(TranslatedDaySection(
                date=day.date, weekday=day.weekday, categories=tcat,
            ))

        return TranslatedCafeteriaMenu(
            cafeteria_id=menu.cafeteria_id,
            cafeteria_name_ko=menu.cafeteria_name_ko,
            cafeteria_name_zh=menu.cafeteria_name_zh,
            cafeteria_name_en=menu.cafeteria_name_en,
            week_start=menu.week_start,
            days=new_days,
            source_url=menu.source_url,
            fetched_at=menu.fetched_at,
            errors=errors,
        )
