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
    minimax_api_key: str
    minimax_group_id: str
    gmail_username: str
    gmail_app_password: str
    mail_to: str


def load_settings() -> Settings:
    def req(key: str) -> str:
        v = os.environ.get(key)
        if not v:
            raise RuntimeError(f"Missing required env var: {key}")
        return v

    return Settings(
        minimax_api_key=req("MINIMAX_API_KEY"),
        minimax_group_id=req("MINIMAX_GROUP_ID"),
        gmail_username=req("GMAIL_USERNAME"),
        gmail_app_password=req("GMAIL_APP_PASSWORD"),
        mail_to=req("MAIL_TO"),
    )
