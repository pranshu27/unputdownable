import hashlib, json
from pathlib import Path
from typing import Any


class SkillCache:
    """
    File-backed cache.
    Key   = SHA-256 of sorted JSON input
    Value = output directory path

    Usage inside skill.run():
        cache = SkillCache()
        hit = cache.get(input_data)
        if hit: return {"output_dir": hit, "files": [], "errors": [], "cached": True}
        ...
        cache.set(input_data, result["output_dir"])
    """

    def __init__(self, cache_file: str = "cache/cache_store.json"):
        self._path = Path(cache_file)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("{}", encoding="utf-8")

    def get(self, data: Any) -> str | None:
        return self._load().get(self._hash(data))

    def set(self, data: Any, output_path: str) -> None:
        store = self._load()
        store[self._hash(data)] = output_path
        self._save(store)

    def clear(self) -> None:
        self._save({})

    def _hash(self, data: Any) -> str:
        s = json.dumps(data, sort_keys=True) if isinstance(data, dict) else str(data)
        return hashlib.sha256(s.encode()).hexdigest()[:16]

    def _load(self) -> dict:
        try:    return json.loads(self._path.read_text(encoding="utf-8"))
        except: return {}

    def _save(self, store: dict) -> None:
        self._path.write_text(json.dumps(store, indent=2), encoding="utf-8")
