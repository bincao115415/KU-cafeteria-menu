import os
from dataclasses import dataclass

CAFETERIAS: list[dict] = [
    {
        "cafeteria_id": "science",
        "source_url": "https://www.korea.ac.kr/ko/504/subview.do",
        "cafeteria_name_ko": "자연계 학생식당",
        "cafeteria_name_zh": "自然科学校区学生食堂",
        "cafeteria_name_en": "Science Campus Student Cafeteria",
        "hours": "",
        "address": "",
    },
    {
        "cafeteria_id": "anam",
        "source_url": "https://www.korea.ac.kr/ko/505/subview.do",
        "cafeteria_name_ko": "안암학사 식당",
        "cafeteria_name_zh": "安岩学舍食堂",
        "cafeteria_name_en": "Anam Dormitory Cafeteria",
        "hours": "",
        "address": "",
    },
    {
        "cafeteria_id": "sanhak",
        "source_url": "https://www.korea.ac.kr/ko/506/subview.do",
        "cafeteria_name_ko": "산학관 식당",
        "cafeteria_name_zh": "产学馆食堂",
        "cafeteria_name_en": "Sanhakgwan Cafeteria",
        "hours": "",
        "address": "",
    },
    {
        "cafeteria_id": "alumni",
        "source_url": "https://www.korea.ac.kr/ko/507/subview.do",
        "cafeteria_name_ko": "교우회관 학생식당",
        "cafeteria_name_zh": "校友会馆学生食堂",
        "cafeteria_name_en": "Alumni Association Student Cafeteria",
        "hours": "",
        "address": "",
    },
    {
        "cafeteria_id": "student_center",
        "source_url": "https://www.korea.ac.kr/ko/508/subview.do",
        "cafeteria_name_ko": "학생회관 학생식당",
        "cafeteria_name_zh": "学生会馆学生食堂",
        "cafeteria_name_en": "Student Center Student Cafeteria",
        "hours": "",
        "address": "",
    },
]


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    gmail_username: str
    gmail_app_password: str
    mail_to: str
    notion_token: str
    notion_parent_page_id: str
    notion_database_id: str
    unsplash_access_key: str | None = None


def load_settings() -> Settings:
    def req(key: str) -> str:
        v = os.environ.get(key)
        if not v:
            raise RuntimeError(f"Missing required env var: {key}")
        return v

    return Settings(
        deepseek_api_key=req("DEEPSEEK_API_KEY"),
        gmail_username=req("GMAIL_USERNAME"),
        gmail_app_password=req("GMAIL_APP_PASSWORD"),
        mail_to=req("MAIL_TO"),
        notion_token=req("NOTION_TOKEN"),
        notion_parent_page_id=req("NOTION_PARENT_PAGE_ID"),
        notion_database_id=req("NOTION_DATABASE_ID"),
        unsplash_access_key=os.environ.get("UNSPLASH_ACCESS_KEY") or None,
    )
