from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Weekday = Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
Confidence = Literal["high", "medium", "low", "failed"]


class DishRaw(BaseModel):
    name_ko: str
    raw_text: str


class DaySection(BaseModel):
    date: date
    weekday: Weekday
    categories: dict[str, list[DishRaw]] = Field(default_factory=dict)


class CafeteriaMenu(BaseModel):
    cafeteria_id: str
    cafeteria_name_ko: str
    cafeteria_name_zh: str
    cafeteria_name_en: str
    week_start: date
    days: list[DaySection]
    source_url: str
    fetched_at: datetime


class WeeklyBundle(BaseModel):
    week_start: date
    cafeterias: list[CafeteriaMenu]


class DishTranslated(BaseModel):
    name_ko: str
    name_zh: str
    name_en: str
    note_zh: str | None = None
    note_en: str | None = None
    is_new: bool = False
    confidence: Confidence = "high"


class TranslatedDaySection(BaseModel):
    date: date
    weekday: Weekday
    categories: dict[str, list[DishTranslated]] = Field(default_factory=dict)


class TranslatedCafeteriaMenu(BaseModel):
    cafeteria_id: str
    cafeteria_name_ko: str
    cafeteria_name_zh: str
    cafeteria_name_en: str
    week_start: date
    days: list[TranslatedDaySection]
    source_url: str
    fetched_at: datetime
    errors: list[str] = Field(default_factory=list)


class TranslatedWeeklyBundle(BaseModel):
    week_start: date
    cafeterias: list[TranslatedCafeteriaMenu]
    new_dish_count: int = 0
    global_errors: list[str] = Field(default_factory=list)
