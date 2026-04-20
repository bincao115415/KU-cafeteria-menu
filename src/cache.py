import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from src.utils import KST

log = logging.getLogger(__name__)


class TranslationCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._schema_version = raw.get("schema_version", 1)
        self._entries: dict[str, dict] = raw.get("entries", {})
        self.new_keys: set[str] = set()

    def get(self, key: str) -> dict | None:
        return self._entries.get(key)

    def set(self, key: str, entry: dict) -> None:
        self._entries[key] = entry
        self.new_keys.add(key)

    def persist(self) -> None:
        payload = {
            "schema_version": self._schema_version,
            "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "entries": dict(sorted(self._entries.items())),
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


class StateFile:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data = json.loads(self.path.read_text(encoding="utf-8"))

    @property
    def last_sent_week(self) -> str | None:
        return self._data.get("last_sent_week")

    @property
    def status(self) -> str:
        return self._data.get("status", "idle")

    def update(self, **kwargs) -> None:
        self._data.update(kwargs)

    def persist(self) -> None:
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def git_commit_and_push(paths: list[Path], message: str, repo_dir: Path) -> bool:
    """Stage, commit, push. Returns True on success. Logs and returns False on failure."""
    try:
        subprocess.run(
            ["git", "-C", str(repo_dir), "add", *[str(p) for p in paths]],
            check=True, capture_output=True,
        )
        r = subprocess.run(
            ["git", "-C", str(repo_dir), "diff", "--cached", "--quiet"],
        )
        if r.returncode == 0:
            log.info("no cache changes to commit")
            return True
        subprocess.run(
            ["git", "-C", str(repo_dir), "commit", "-m", message],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_dir), "push"],
            check=True, capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        log.warning("git commit/push failed: %s", e.stderr.decode(errors="replace"))
        return False
