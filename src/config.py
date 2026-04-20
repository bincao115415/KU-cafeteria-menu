import os
from dataclasses import dataclass

CAFETERIAS: list[dict] = [
    {
        "cafeteria_id": "songnim",
        "source_url": "https://www.korea.ac.kr/ko/503/subview.do",
        "cafeteria_name_ko": "수당삼양 Faculty House 송림",
        "cafeteria_name_zh": "수당삼양教职工之家 松林",
        "cafeteria_name_en": "Sudang-Samyang Faculty House Songnim",
        "hours": "Lunch 11:00-14:00 · Dinner 17:00-21:00",
    },
    {
        "cafeteria_id": "science",
        "source_url": "https://www.korea.ac.kr/ko/TBD_SCIENCE/subview.do",
        "cafeteria_name_ko": "이공계캠퍼스 학생식당",
        "cafeteria_name_zh": "理工校区学生食堂",
        "cafeteria_name_en": "Science Campus Student Cafeteria",
        "hours": "",
    },
    {
        "cafeteria_id": "anam",
        "source_url": "https://www.korea.ac.kr/ko/TBD_ANAM/subview.do",
        "cafeteria_name_ko": "안암학사 식당",
        "cafeteria_name_zh": "安岩宿舍食堂",
        "cafeteria_name_en": "Anam Dormitory Cafeteria",
        "hours": "",
    },
    {
        "cafeteria_id": "sanhak",
        "source_url": "https://www.korea.ac.kr/ko/TBD_SANHAK/subview.do",
        "cafeteria_name_ko": "산학관 식당",
        "cafeteria_name_zh": "产学馆食堂",
        "cafeteria_name_en": "Sanhakgwan Cafeteria",
        "hours": "",
    },
    {
        "cafeteria_id": "alumni",
        "source_url": "https://www.korea.ac.kr/ko/TBD_ALUMNI/subview.do",
        "cafeteria_name_ko": "교우회관 식당",
        "cafeteria_name_zh": "校友会馆食堂",
        "cafeteria_name_en": "Alumni Association Cafeteria",
        "hours": "",
    },
    {
        "cafeteria_id": "student_center",
        "source_url": "https://www.korea.ac.kr/ko/TBD_SC/subview.do",
        "cafeteria_name_ko": "학생회관 식당",
        "cafeteria_name_zh": "学生会馆食堂",
        "cafeteria_name_en": "Student Center Cafeteria",
        "hours": "",
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
