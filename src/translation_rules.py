from __future__ import annotations

from copy import deepcopy

NON_MENU_ITEM_MARKERS = {
    "미운영",
}

_EXACT_TRANSLATION_OVERRIDES: dict[str, dict[str, str | None]] = {
    "1회용김": {
        "zh": "即食海苔",
        "en": "Roasted Seaweed Pack",
        "note_zh": "单独包装的调味或烤海苔。",
        "note_en": "Individually packaged seasoned or roasted seaweed.",
    },
    "피클": {
        "zh": "酸黄瓜",
        "en": "Pickles",
        "note_zh": "西式腌黄瓜或腌蔬菜配菜。",
        "note_en": "Western-style pickled cucumber or mixed vegetables.",
    },
    "유부장국": {
        "zh": "油豆腐清汤",
        "en": "Clear Soup with Fried Tofu",
        "note_zh": "加入油豆腐的清汤或日式风味汤。",
        "note_en": "A light broth served with fried tofu pouches.",
    },
    "현대에너지바": {
        "zh": "现代能量棒",
        "en": "Hyundai Energy Bar",
        "note_zh": "包装能量棒或谷物棒。",
        "note_en": "A packaged energy or cereal bar.",
    },
    "쥐어채볶음": {
        "zh": "炒调味鱼干丝",
        "en": "Stir-fried Seasoned Filefish Strips",
        "note_zh": "以调味鱼干丝炒制的小菜。",
        "note_en": "A side dish made from seasoned dried filefish strips.",
    },
    "가쓰오부시타코야끼": {
        "zh": "木鱼花章鱼小丸子",
        "en": "Takoyaki with Bonito Flakes",
        "note_zh": "上面撒有木鱼花的章鱼小丸子。",
        "note_en": "Takoyaki topped with bonito flakes.",
    },
}


def apply_translation_overrides(name_ko: str, entry: dict | None) -> dict | None:
    if entry is None:
        return None

    override = _EXACT_TRANSLATION_OVERRIDES.get(name_ko)
    if override is None:
        return entry

    out = deepcopy(entry)
    out.update(override)
    out["confidence"] = "high"
    out["search_confirmed"] = True
    source = str(out.get("source", "manual-override"))
    out["source"] = source if source.endswith("+manual-override") or source == "manual-override" else f"{source}+manual-override"
    return out
