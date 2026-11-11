import os
from dataclasses import dataclass

_HIDDEN_CATEGORIES = {"조식", "천원의아침", "천원의아침(테이크아웃)", "아침"}

_HERO_BASE = (
    "https://raw.githubusercontent.com/"
    "bincao115415/KU-cafeteria-menu/main/data/photos/heroes"
)


def _hero(name: str) -> str:
    return f"{_HERO_BASE}/{name}.jpg"


CAFETERIAS: list[dict] = [
    {
        "cafeteria_id": "science_student",
        "source_url": "https://www.korea.ac.kr/ko/504/subview.do",
        "cafeteria_name_ko": "자연계 학생식당 (학생)",
        "cafeteria_name_zh": "自然科学校区学生食堂",
        "cafeteria_name_en": "Science Student Cafeteria",
        "section_filter": "학생식당",
        "price_krw": 6000,
        "allowed_meals": ["午餐"],
        "hero_image_url": _hero("science"),
        "hours": "",
        "address": "",
    },
    {
        "cafeteria_id": "science_faculty",
        "source_url": "https://www.korea.ac.kr/ko/504/subview.do",
        "cafeteria_name_ko": "자연계 학생식당 (교직원)",
        "cafeteria_name_zh": "自然科学校区教职员食堂",
        "cafeteria_name_en": "Science Faculty Cafeteria",
        "section_filter": "교직원식당",
        "price_krw": 7000,
        "allowed_meals": ["午餐", "晚餐"],
        "hero_image_url": _hero("science"),
        "hours": "",
        "address": "",
    },
    {
        "cafeteria_id": "anam",
        "source_url": "https://www.korea.ac.kr/ko/505/subview.do",
        "cafeteria_name_ko": "안암학사 식당",
        "cafeteria_name_zh": "安岩学舍食堂",
        "cafeteria_name_en": "Anam Dormitory Cafeteria",
        "section_filter": None,
        "price_krw": None,
        "allowed_meals": ["午餐", "晚餐"],
        "hero_image_url": _hero("anam"),
        "hours": "",
        "address": "",
    },
    {
        "cafeteria_id": "sanhak",
        "source_url": "https://www.korea.ac.kr/ko/506/subview.do",
        "cafeteria_name_ko": "산학관 식당",
        "cafeteria_name_zh": "产学馆食堂",
        "cafeteria_name_en": "Sanhakgwan Cafeteria",
        "section_filter": None,
        "price_krw": None,
        "allowed_meals": ["午餐", "晚餐"],
        "hero_image_url": _hero("sanhak"),
        "hours": "",
        "address": "",
    },
    {
        "cafeteria_id": "student_center",
        "source_url": "https://www.korea.ac.kr/ko/508/subview.do",
        "cafeteria_name_ko": "학생회관 학생식당",
        "cafeteria_name_zh": "学生会馆学生食堂",
        "cafeteria_name_en": "Student Center Student Cafeteria",
        "section_filter": None,
        "price_krw": None,
        "allowed_meals": ["午餐", "晚餐"],
        "hero_image_url": _hero("student_center"),
        "hours": "",
        "address": "",
    },
]


def is_published_category(cafeteria_id: str, category: str) -> bool:
    if category in _HIDDEN_CATEGORIES:
        return False
    cfg = next((c for c in CAFETERIAS if c["cafeteria_id"] == cafeteria_id), {})
    meal = "晚餐" if "석식" in category else "午餐"
    return meal in (cfg.get("allowed_meals") or ["午餐", "晚餐"])


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    notion_token: str
    notion_parent_page_id: str
    notion_database_id: str
    unsplash_access_key: str | None = None


def load_settings(*, require_notion: bool = True) -> Settings:
    def req(key: str) -> str:
        v = os.environ.get(key)
        if not v:
            raise RuntimeError(f"Missing required env var: {key}")
        return v

    return Settings(
        deepseek_api_key=req("DEEPSEEK_API_KEY"),
        notion_token=req("NOTION_TOKEN") if require_notion else "",
        notion_parent_page_id=req("NOTION_PARENT_PAGE_ID") if require_notion else "",
        notion_database_id=req("NOTION_DATABASE_ID") if require_notion else "",
        unsplash_access_key=os.environ.get("UNSPLASH_ACCESS_KEY") or None,
    )
