from __future__ import annotations

from copy import deepcopy

NON_MENU_ITEM_MARKERS = {
    "미운영",
}

_EXACT_TRANSLATION_OVERRIDES: dict[str, dict[str, str | None]] = {
    # Sources and rationale: docs/plans/2026-11-11-publish-retry-translation-quality.md
    "불닭볶음우동": {
        "zh": "韩式辣鸡风味炒乌冬面", "en": "Buldak Stir-fried Udon",
        "note_zh": "불닭 指韩式辣鸡风味；原文未说明是否含鸡肉。",
        "note_en": "Buldak-style spicy udon; the menu does not specify whether chicken meat is included.",
    },
    "하이라이스": {
        "zh": "日式洋风烩饭", "en": "Hayashi Rice",
        "note_zh": "洋风酱汁烩饭，原文未说明所用肉类。",
        "note_en": "Rice served with a Western-style brown sauce; meat is not specified.",
    },
    "돈육하이라이스": {
        "zh": "猪肉洋风烩饭", "en": "Pork Hayashi Rice",
        "note_zh": "猪肉配洋风酱汁和米饭。", "note_en": "Pork and rice with Hayashi-style sauce.",
    },
    "B돈육하이라이스": {
        "zh": "猪肉洋风烩饭", "en": "Pork Hayashi Rice",
        "note_zh": "猪肉配洋风酱汁和米饭。", "note_en": "Pork and rice with Hayashi-style sauce.",
    },
    "소시지하이라이스": {
        "zh": "香肠洋风烩饭", "en": "Sausage Hayashi Rice",
        "note_zh": "香肠配洋风酱汁和米饭。", "note_en": "Sausage and rice with Hayashi-style sauce.",
    },
    "스크램블하이라이스": {
        "zh": "炒蛋洋风烩饭", "en": "Scrambled Egg Hayashi Rice",
        "note_zh": "炒蛋配洋风酱汁和米饭。", "note_en": "Scrambled egg and rice with Hayashi-style sauce.",
    },
    "치킨까스하이라이스": {
        "zh": "炸鸡排洋风烩饭", "en": "Chicken Cutlet Hayashi Rice",
        "note_zh": "炸鸡排配洋风酱汁和米饭。", "note_en": "Chicken cutlet with Hayashi rice.",
    },
    "돈가스&하이라이스": {
        "zh": "炸猪排配洋风烩饭", "en": "Pork Cutlet and Hayashi Rice",
        "note_zh": "炸猪排搭配洋风烩饭。", "note_en": "Pork cutlet served with Hayashi rice.",
    },
    "하이라이스덮밥": {
        "zh": "日式洋风盖饭", "en": "Hayashi Rice Bowl",
        "note_zh": "米饭浇洋风酱汁，原文未说明所用肉类。",
        "note_en": "Rice topped with Hayashi-style sauce; meat is not specified.",
    },
    "하와이안로코모코": {
        "zh": "夏威夷肉饼煎蛋盖饭", "en": "Hawaiian Loco Moco",
        "note_zh": "通常为米饭配肉饼、煎蛋和肉汁。",
        "note_en": "Traditionally rice topped with a hamburger patty, egg and gravy.",
    },
    "헐랭이수육": {
        "zh": "白切肉（헐랭이，待核对）", "en": "Boiled Meat (헐랭이; needs review)",
        "note_zh": "原文未明确肉类部位；헐랭이 的含义待食堂确认。",
        "note_en": "The meat cut and the meaning of 헐랭이 need confirmation from the cafeteria.",
        "confidence": "low",
    },
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
    override = _EXACT_TRANSLATION_OVERRIDES.get(name_ko)
    if override is None:
        return entry

    out = deepcopy(entry) if entry else {}
    out.update(override)
    out["confidence"] = override.get("confidence", "high")
    out["search_confirmed"] = False
    source = str(out.get("source", "manual-override"))
    out["source"] = source if source.endswith("+manual-override") or source == "manual-override" else f"{source}+manual-override"
    return out


def valid_translation(entry: dict) -> bool:
    return all(
        isinstance(entry.get(field), str)
        and bool(entry[field].strip())
        and "[translation failed]" not in entry[field].lower()
        for field in ("zh", "en")
    )
