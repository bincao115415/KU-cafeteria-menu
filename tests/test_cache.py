import json

import pytest

from src.cache import StateFile, TranslationCache


def _entry(**over) -> dict:
    base = {
        "zh": "大酱汤",
        "en": "Soybean Paste Stew",
        "note_zh": None,
        "note_en": None,
        "learned_at": "2026-04-20",
        "source": "minimax-two-pass",
        "search_confirmed": True,
        "confidence": "high",
    }
    base.update(over)
    return base


@pytest.fixture
def tmp_cache(tmp_path):
    p = tmp_path / "translations.json"
    p.write_text(json.dumps({"schema_version": 1, "updated_at": "x", "entries": {}}))
    return TranslationCache(path=p)


def test_cache_get_miss_returns_none(tmp_cache):
    assert tmp_cache.get("된장찌개") is None


def test_cache_set_and_get(tmp_cache):
    tmp_cache.set("된장찌개", _entry())
    hit = tmp_cache.get("된장찌개")
    assert hit["zh"] == "大酱汤"


def test_cache_persist_writes_to_disk(tmp_cache, tmp_path):
    tmp_cache.set("A", _entry(zh="甲", en="A"))
    tmp_cache.persist()
    disk = json.loads((tmp_path / "translations.json").read_text())
    assert disk["entries"]["A"]["zh"] == "甲"
    assert disk["updated_at"] != "x"  # updated timestamp changed


def test_cache_new_keys_tracked(tmp_cache):
    tmp_cache.set("A", _entry(zh="甲", en="A"))
    assert "A" in tmp_cache.new_keys


def test_cache_existing_entries_loaded(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({
        "schema_version": 1, "updated_at": "x",
        "entries": {"된장찌개": _entry()},
    }))
    c = TranslationCache(path=p)
    assert c.get("된장찌개")["zh"] == "大酱汤"
    assert "된장찌개" not in c.new_keys  # preexisting, not newly learned


def test_state_read_and_write(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"last_sent_week": None, "last_run_at": None, "status": "idle"}))
    s = StateFile(path=p)
    assert s.status == "idle"
    assert s.last_sent_week is None
    s.update(last_sent_week="2026-04-20", status="done", last_run_at="2026-04-20T10:30:00+09:00")
    s.persist()
    disk = json.loads(p.read_text())
    assert disk["status"] == "done"
    assert disk["last_sent_week"] == "2026-04-20"
