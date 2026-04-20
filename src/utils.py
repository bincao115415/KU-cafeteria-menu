import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

_MIDDLE_DOTS = str.maketrans({"・": "·", "‧": "·"})


def normalize_dish_name(name: str) -> str:
    s = name.translate(_MIDDLE_DOTS)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        raise ValueError("dish name is empty after normalization")
    return s


def get_current_monday_kst() -> date:
    now = datetime.now(KST)
    return (now - timedelta(days=now.weekday())).date()
