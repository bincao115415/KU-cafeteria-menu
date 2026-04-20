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
    s = load_settings()
    assert s.deepseek_api_key == "k"
    assert s.gmail_username == "u@x"
    assert s.mail_to == "to@x"


def test_load_settings_missing_key_raises(monkeypatch):
    import pytest
    for k in ["DEEPSEEK_API_KEY", "GMAIL_USERNAME", "GMAIL_APP_PASSWORD", "MAIL_TO"]:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        load_settings()
