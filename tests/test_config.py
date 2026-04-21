from src.config import CAFETERIAS, load_settings


def test_cafeterias_count_is_five():
    assert len(CAFETERIAS) == 5


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
    monkeypatch.setenv("GMAIL_USERNAME", "u@x")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "p")
    monkeypatch.setenv("MAIL_TO", "to@x")
    monkeypatch.setenv("NOTION_TOKEN", "ntn_x")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "pid")
    monkeypatch.setenv("NOTION_DATABASE_ID", "dbid")
    s = load_settings()
    assert s.deepseek_api_key == "k"
    assert s.gmail_username == "u@x"
    assert s.mail_to == "to@x"


def test_load_settings_missing_key_raises(monkeypatch):
    import pytest
    for k in [
        "DEEPSEEK_API_KEY", "GMAIL_USERNAME", "GMAIL_APP_PASSWORD", "MAIL_TO",
        "NOTION_TOKEN", "NOTION_PARENT_PAGE_ID", "NOTION_DATABASE_ID",
        "UNSPLASH_ACCESS_KEY",
    ]:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        load_settings()


def test_load_settings_with_notion_fields(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dk")
    monkeypatch.setenv("GMAIL_USERNAME", "u@x")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "p")
    monkeypatch.setenv("MAIL_TO", "to@x")
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
        "GMAIL_USERNAME": "u@x",
        "GMAIL_APP_PASSWORD": "p",
        "MAIL_TO": "to@x",
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
        "GMAIL_USERNAME": "u@x",
        "GMAIL_APP_PASSWORD": "p",
        "MAIL_TO": "to@x",
        "NOTION_PARENT_PAGE_ID": "pid",
        "NOTION_DATABASE_ID": "dbid",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    from src.config import load_settings
    import pytest
    with pytest.raises(RuntimeError, match=r"Missing required env var: NOTION_TOKEN"):
        load_settings()
