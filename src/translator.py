import asyncio
import logging
import re
from datetime import datetime
from typing import Protocol

from src.cache import TranslationCache
from src.config import is_published_category
from src.models import (
    CafeteriaMenu,
    DishRaw,
    DishTranslated,
    TranslatedCafeteriaMenu,
    TranslatedDaySection,
)
from src.translation_rules import apply_translation_overrides, valid_translation
from src.utils import KST, normalize_dish_name

log = logging.getLogger(__name__)

_SYSTEM_PASS1 = """你是韩国餐饮翻译专家。给出一个韩国料理菜名的中文名、英文名,以及一句成分/做法说明。
- 中文名优先使用中国大陆常见译法(例如 된장찌개 → 大酱汤, 而不是字面直译)。
- 英文名使用餐饮业常见英文说法(例如 Soybean Paste Stew)。
- note_zh 和 note_en 是可选的一句话成分说明, <=30 字/单词。
- 保留原文的菜品、肉类和做法，不补充未注明的肉类部位、食材或品牌故事。不确定时保留韩文限定词，并在说明中指出待核对。
- 불닭 是韩式辣鸡风味，不是火鸡肉；하이라이스 是 Hayashi Rice，不是咖喱饭；로코모코 是肉饼煎蛋盖饭，不是夹米饭的汉堡。
- 中文和英文均须为非空字符串；菜名前的宣传性人名不必译出。
严格只输出 JSON:{"zh": "...", "en": "...", "note_zh": "... or null", "note_en": "... or null"}。"""

_SYSTEM_PASS2 = """你在审阅另一个 LLM 对韩国料理菜名的翻译。凭你对韩餐和中/英餐饮用语的掌握,判断它是否是中国大陆/国际餐饮业里的标准/惯用说法。
给出裁定:
- 逐项核对原文中的主食、食材、肉类、做法及限定词是否保留；检查译文是否遗漏、添加或混淆菜品。
- 不认识的专名或无法确认的肉类部位使用 no_signal，不要凭猜测补全。此步骤没有联网检索，不能声称已查证。
- "confirm" 如果原译已是常用/惯用说法(例如 된장찌개 → 大酱汤);
- "revise" 如果你确信有更通用的译法(在 revised 字段里给出新的 zh/en/note_zh/note_en);
- "no_signal" 如果你不确定。
严格只输出 JSON:{"verdict": "confirm"|"revise"|"no_signal", "revised": {...}}。revised 仅在 verdict==revise 时需要。"""

_SYSTEM_SPLIT = """你在整理韩国大学食堂菜单。输入可能是单个菜名, 也可能是一整行套餐菜单。
任务: 只输出 JSON:{"items": ["韩文菜名1", "韩文菜名2", ...]}。
规则:
- 如果输入本来就是单个菜名, 返回单元素数组。
- 如果输入是一整行套餐, 按上菜顺序拆成单独菜名。
- 保留韩文原文, 不要翻译, 不要改写。
- 完整保留所有菜品及其顺序；不得添加、遗漏、改写或重复原文中的字词。
- 酱汁和做法应尽量与所属菜品放在同一项，不要把 '치킨까스*허니머스타드' 拆成两道菜。
- 输入已去除价格、产地和宣传性人名抬头，保留其余原文。"""


class ChatClient(Protocol):
    async def chat_json(self, user: str, *, system: str | None = None) -> dict: ...
    async def chat_reflect(self, user: str, *, system: str | None = None) -> dict: ...


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

    @staticmethod
    def _looks_like_compound_line(name: str) -> bool:
        stripped = name.strip()
        if " / " in stripped:
            return True
        return len(stripped.split()) >= 4

    @staticmethod
    def _normalized_segment_items(payload: dict, fallback: str) -> list[str]:
        raw_items = payload.get("items") or payload.get("dishes") or []
        if not isinstance(raw_items, list) or not raw_items or any(
            not isinstance(item, str) or not item.strip() for item in raw_items
        ):
            raise ValueError("invalid menu split: expected nonempty Korean strings")
        items = [item.strip() for item in raw_items]
        # Ignore separators, but require every original letter/digit in order.
        source = "".join(ch for ch in fallback if ch.isalnum())
        segmented = "".join(ch for item in items for ch in item if ch.isalnum())
        if source != segmented:
            raise ValueError("invalid menu split: changed or omitted source text")
        return items

    async def _expand_raw_dish(self, raw: DishRaw) -> list[DishRaw]:
        name = re.sub(r"^\S+이의\s+", "", raw.name_ko.strip())
        if not self._looks_like_compound_line(name):
            return [raw]
        try:
            async with self._sem:
                split = await self.client.chat_json(
                    f"메뉴 줄:{name}",
                    system=_SYSTEM_SPLIT,
                )
            items = self._normalized_segment_items(split, name)
            return [DishRaw(name_ko=item, raw_text=raw.raw_text) for item in items]
        except Exception as e:
            log.warning("menu split failed for %s: %s", raw.name_ko, e)
            raise ValueError(f"menu split failed for {raw.name_ko}") from e

    async def translate_menu(self, menu: CafeteriaMenu) -> TranslatedCafeteriaMenu:
        errors: list[str] = []
        visible_days = [
            {cat: dishes for cat, dishes in day.categories.items()
             if is_published_category(menu.cafeteria_id, cat)}
            for day in menu.days
        ]

        unique_raws: dict[str, DishRaw] = {}
        for categories in visible_days:
            for cat_dishes in categories.values():
                for d in cat_dishes:
                    unique_raws.setdefault(d.name_ko, d)

        expanded_results = await asyncio.gather(*[
            self._expand_raw_dish(raw) for raw in unique_raws.values()
        ])
        expanded_by_raw = dict(zip(unique_raws.keys(), expanded_results, strict=True))

        normalized_days: list[dict[str, list[DishRaw]]] = []
        for categories in visible_days:
            expanded_categories: dict[str, list[DishRaw]] = {}
            for cat, ds in categories.items():
                expanded: list[DishRaw] = []
                for d in ds:
                    expanded.extend(expanded_by_raw.get(d.name_ko, [d]))
                expanded_categories[cat] = expanded
            normalized_days.append(expanded_categories)

        unique_keys: dict[str, DishRaw] = {}
        for categories in normalized_days:
            for cat_dishes in categories.values():
                for d in cat_dishes:
                    try:
                        k = normalize_dish_name(d.name_ko)
                    except ValueError:
                        continue
                    unique_keys.setdefault(k, d)

        async def resolve(key: str, raw: DishRaw) -> tuple[str, DishTranslated]:
            async with self._sem:
                is_new = key not in self.cache
                hit = self.cache.get(key)
                if hit is not None:
                    return key, DishTranslated(
                        name_ko=raw.name_ko,
                        name_zh=hit["zh"],
                        name_en=hit["en"],
                        note_zh=hit.get("note_zh"),
                        note_en=hit.get("note_en"),
                        is_new=is_new,
                        confidence=hit.get("confidence", "high"),
                    )
                try:
                    p1 = await self.client.chat_json(
                        f"菜名:{raw.name_ko}", system=_SYSTEM_PASS1,
                    )
                    if not valid_translation(p1):
                        raise ValueError("translation requires nonempty Chinese and English names")
                    p2 = await self.client.chat_reflect(
                        f"菜名韩文:{raw.name_ko}\n初版翻译:{p1}",
                        system=_SYSTEM_PASS2,
                    )
                    verdict = p2.get("verdict", "no_signal")
                    revised = p2.get("revised")
                    if verdict == "confirm":
                        chosen, confidence = p1, "high"
                    elif verdict == "revise" and isinstance(revised, dict) and valid_translation(revised):
                        chosen, confidence = revised, "medium"
                    else:
                        chosen, confidence, verdict = p1, "low", "no_signal"

                    entry = {
                        "zh": chosen["zh"].strip(),
                        "en": chosen["en"].strip(),
                        "note_zh": _norm_note(chosen.get("note_zh")),
                        "note_en": _norm_note(chosen.get("note_en")),
                        "learned_at": datetime.now(KST).date().isoformat(),
                        "source": "deepseek-two-pass",
                        "search_confirmed": False,
                        "review_verdict": verdict,
                        "confidence": confidence,
                    }
                    entry = apply_translation_overrides(key, entry) or entry
                    translated = DishTranslated(
                        name_ko=raw.name_ko,
                        name_zh=entry["zh"],
                        name_en=entry["en"],
                        note_zh=entry["note_zh"],
                        note_en=entry["note_en"],
                        is_new=is_new,
                        confidence=entry["confidence"],
                    )
                    self.cache.set(key, entry)
                    return key, translated
                except Exception as e:
                    log.warning("translate failed for %s: %s", raw.name_ko, e)
                    errors.append(f"{raw.name_ko}: {e}")
                    return key, DishTranslated(
                        name_ko=raw.name_ko,
                        name_zh="[translation failed]",
                        name_en="[translation failed]",
                        is_new=is_new,
                        confidence="failed",
                    )

        results = await asyncio.gather(*[resolve(k, d) for k, d in unique_keys.items()])
        resolved_by_key = {k: dt for k, dt in results}

        new_days: list[TranslatedDaySection] = []
        for day, categories in zip(menu.days, normalized_days, strict=True):
            tcat: dict[str, list[DishTranslated]] = {}
            for cat, ds in categories.items():
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
