from src.config import CAFETERIAS, load_settings


def test_cafeterias_count_is_six():
    # 4 single-section cafeterias + 2 sub-menus of science (student/faculty)
    assert len(CAFETERIAS) == 6


def test_science_split_into_student_and_faculty():
    ids = {c["cafeteria_id"] for c in CAFETERIAS}
    assert "science_student" in ids
    assert "science_faculty" in ids
    assert "science" not in ids
    sci = [c for c in CAFETERIAS if c["cafeteria_id"].startswith("science_")]
    assert {c["source_url"] for c in sci} == {"https://www.korea.ac.kr/ko/504/subview.do"}
    prices = {c["cafeteria_id"]: c["price_krw"] for c in sci}
    assert prices == {"science_student": 6000, "science_faculty": 7000}
    filters = {c["cafeteria_id"]: c["section_filter"] for c in sci}
    assert filters == {"science_student": "학생식당", "science_faculty": "교직원식당"}


def test_cafeterias_have_required_fields():
    for c in CAFETERIAS:
        assert c["cafeteria_id"]
        assert c["source_url"].startswith("https://www.korea.ac.kr/")
        assert c["cafeteria_name_ko"]
        assert c["cafeteria_name_zh"]
        assert c["cafeteria_name_en"]
        assert "address" in c


def test_songnim_removed():
    assert all(c["cafeteria_id"] != "songnim" for c in CAFETERIAS)


def test_cafeteria_ids_are_unique():
    ids = [c["cafeteria_id"] for c in CAFETERIAS]
    assert len(ids) == len(set(ids))


def test_load_settings_reads_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setenv("NOTION_TOKEN", "ntn_x")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "pid")
    monkeypatch.setenv("NOTION_DATABASE_ID", "dbid")
    s = load_settings()
    assert s.deepseek_api_key == "k"
    assert s.notion_token == "ntn_x"
    assert s.notion_parent_page_id == "pid"
    assert s.notion_database_id == "dbid"


def test_load_settings_missing_key_raises(monkeypatch):
    import pytest
    for k in [
        "DEEPSEEK_API_KEY",
        "NOTION_TOKEN", "NOTION_PARENT_PAGE_ID", "NOTION_DATABASE_ID",
        "UNSPLASH_ACCESS_KEY",
    ]:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        load_settings()


def test_load_settings_with_notion_fields(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dk")
    monkeypatch.setenv("NOTION_TOKEN", "ntn_x")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "pid")
    monkeypatch.setenv("NOTION_DATABASE_ID", "dbid")

    from src.config import load_settings
    s = load_settings()
    assert s.notion_token == "ntn_x"
    assert s.notion_parent_page_id == "pid"
    assert s.notion_database_id == "dbid"
    assert s.unsplash_access_key is None  # optional, default None


def test_load_settings_with_unsplash(monkeypatch):
    for k, v in {
        "DEEPSEEK_API_KEY": "dk",
        "NOTION_TOKEN": "ntn_x",
        "NOTION_PARENT_PAGE_ID": "pid",
        "NOTION_DATABASE_ID": "dbid",
        "UNSPLASH_ACCESS_KEY": "us_key",
    }.items():
        monkeypatch.setenv(k, v)
    from src.config import load_settings
    assert load_settings().unsplash_access_key == "us_key"


def test_load_settings_missing_notion_token_raises(monkeypatch):
    for k, v in {
        "DEEPSEEK_API_KEY": "dk",
        "NOTION_PARENT_PAGE_ID": "pid",
        "NOTION_DATABASE_ID": "dbid",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    import pytest

    from src.config import load_settings
    with pytest.raises(RuntimeError, match=r"Missing required env var: NOTION_TOKEN"):
        load_settings()
