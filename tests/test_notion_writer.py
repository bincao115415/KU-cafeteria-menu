from datetime import date, datetime

from src.models import (
    DishTranslated,
    TranslatedCafeteriaMenu,
    TranslatedDaySection,
    TranslatedWeeklyBundle,
)
from src.notion_writer import classify_meal, group_into_meals


def _bundle_with_dishes(categories: dict[str, list[DishTranslated]]) -> TranslatedWeeklyBundle:
    day = TranslatedDaySection(
        date=date(2026, 4, 20), weekday="MON", categories=categories
    )
    cm = TranslatedCafeteriaMenu(
        cafeteria_id="science",
        cafeteria_name_ko="자연계", cafeteria_name_zh="自然科学", cafeteria_name_en="Science",
        week_start=date(2026, 4, 20),
        days=[day],
        source_url="https://example.com/s",
        fetched_at=datetime(2026, 4, 20, 9, 0),
    )
    return TranslatedWeeklyBundle(week_start=date(2026, 4, 20), cafeterias=[cm])


def test_classify_meal_by_korean_label():
    assert classify_meal("중식B") == "午餐"
    assert classify_meal("석식") == "晚餐"
    assert classify_meal("석식A") == "晚餐"
    assert classify_meal("파스타/스테이크 코스") == "午餐"


def test_group_splits_lunch_and_dinner():
    dishes_lunch = [DishTranslated(name_ko="김치찌개", name_zh="泡菜汤", name_en="Kimchi Stew")]
    dishes_dinner = [DishTranslated(name_ko="불고기", name_zh="烤肉", name_en="Bulgogi")]
    bundle = _bundle_with_dishes({"중식B": dishes_lunch, "석식": dishes_dinner})

    meals = group_into_meals(bundle, lambda cid, ko, en: None)

    assert len(meals) == 2
    meal_by = {m["meal"]: m for m in meals}
    assert meal_by["午餐"]["dish_count"] == 1
    assert meal_by["晚餐"]["dish_count"] == 1
    assert meal_by["午餐"]["categories"][0]["label_ko"] == "중식B"
    assert meal_by["晚餐"]["categories"][0]["label_ko"] == "석식"


def test_group_filters_hidden_breakfast_categories():
    dishes = [DishTranslated(name_ko="토스트", name_zh="吐司", name_en="Toast")]
    bundle = _bundle_with_dishes({"조식": dishes, "천원의아침": dishes, "아침": dishes})
    assert group_into_meals(bundle, lambda *a, **k: None) == []


def test_group_counts_new_dishes():
    dishes = [
        DishTranslated(name_ko="A", name_zh="A", name_en="A", is_new=True),
        DishTranslated(name_ko="B", name_zh="B", name_en="B", is_new=False),
        DishTranslated(name_ko="C", name_zh="C", name_en="C", is_new=True),
    ]
    bundle = _bundle_with_dishes({"중식B": dishes})
    [meal] = group_into_meals(bundle, lambda *a, **k: None)
    assert meal["dish_count"] == 3
    assert meal["new_count"] == 2


def test_group_confidence_is_worst_case():
    dishes = [
        DishTranslated(name_ko="A", name_zh="A", name_en="A", confidence="high"),
        DishTranslated(name_ko="B", name_zh="B", name_en="B", confidence="low"),
        DishTranslated(name_ko="C", name_zh="C", name_en="C", confidence="medium"),
    ]
    bundle = _bundle_with_dishes({"중식B": dishes})
    [meal] = group_into_meals(bundle, lambda *a, **k: None)
    assert meal["confidence"] == "low"


def test_group_attaches_photo_urls():
    dishes = [
        DishTranslated(name_ko="김치", name_zh="泡菜", name_en="Kimchi"),
        DishTranslated(name_ko="밥", name_zh="米饭", name_en="Rice"),
    ]
    bundle = _bundle_with_dishes({"중식B": dishes})

    def resolver(cid, ko, en):
        return f"https://example.com/{cid}/{ko}.jpg" if ko == "김치" else None

    [meal] = group_into_meals(bundle, resolver)
    photos = [ln["photo_url"] for blk in meal["categories"] for ln in blk["dishes"]]
    assert photos == ["https://example.com/science/김치.jpg", None]


def test_group_skips_weekend_days():
    sat = TranslatedDaySection(date=date(2026, 4, 25), weekday="SAT", categories={
        "중식B": [DishTranslated(name_ko="A", name_zh="A", name_en="A")]
    })
    cm = TranslatedCafeteriaMenu(
        cafeteria_id="science",
        cafeteria_name_ko="x", cafeteria_name_zh="x", cafeteria_name_en="x",
        week_start=date(2026, 4, 20), days=[sat],
        source_url="u", fetched_at=datetime(2026, 4, 20, 9, 0),
    )
    bundle = TranslatedWeeklyBundle(week_start=date(2026, 4, 20), cafeterias=[cm])
    assert group_into_meals(bundle, lambda *a, **k: None) == []
