"""RunRecorder — persist every step of a pipeline run to disk.

Layout produced per run::

    runs/<timestamp>_<mapping>/
        manifest.json                 # run metadata + ordered index of artifacts
        00_parsed_nodes.json          # canonical nodes parsed from the PowerCenter XML
        01_redacted_nodes.json        # nodes after input guardrails (PII/secret redaction)
        02_rag_context.txt            # cross-file context string handed to the modeller
        02_rag_hits.json              # structured retrieval hits for the focus query
        03_extracted_nodes.json       # normalized nodes after the extraction barrier
        llm/
            01_data_modeller.input.json
            01_data_modeller.output.txt
            02_pyspark_generation.input.json
            02_pyspark_generation.output.txt
            ...
        99_final_result.json          # the orchestrator FinalResult

Everything is best-effort: a failure to write an artifact never breaks the pipeline.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

# e2e_infa_to_pyspark/  (this file is app/observability/run_recorder.py)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _slug(text: str) -> str:
    keep = [c if (c.isalnum() or c in ("-", "_")) else "_" for c in (text or "")]
    return "".join(keep)[:80] or "step"


def _safe_json(data: Any) -> str:
    try:
        return json.dumps(data, indent=2, default=str, ensure_ascii=False)
    except Exception:
        return json.dumps({"_unserializable": str(data)}, indent=2)


class RunRecorder:
    """Writes ordered run artifacts under ``runs/<timestamp>_<mapping>/``.

    Thread-safety: the single-threaded autogen runtime calls this sequentially, but an
    internal lock keeps the LLM counter consistent regardless.
    """

    def __init__(
        self,
        mapping: Optional[str] = None,
        base_dir: Optional[Path] = None,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self._lock = threading.Lock()
        self._llm_counter = 0
        self._index: List[Dict[str, Any]] = []
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = base_dir or (_PROJECT_ROOT / "runs")
        self.run_dir = base / f"{ts}_{_slug(mapping or 'mapping')}"
        self.llm_dir = self.run_dir / "llm"
        if self.enabled:
            try:
                self.llm_dir.mkdir(parents=True, exist_ok=True)
                logger.info("Run artifacts -> %s", self.run_dir)
            except Exception as exc:  # pragma: no cover - disk failure
                logger.warning("Could not create run dir, recording disabled: %s", exc)
                self.enabled = False

    # --- pipeline-level artifacts ---------------------------------------------------

    def save_json(self, name: str, data: Any) -> None:
        if not self.enabled:
            return
        fname = f"{_slug(name)}.json"
        try:
            (self.run_dir / fname).write_text(_safe_json(data), encoding="utf-8")
            self._index.append({"artifact": fname, "kind": "json"})
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to record %s: %s", fname, exc)

    def save_text(self, name: str, text: str) -> None:
        if not self.enabled:
            return
        fname = f"{_slug(name)}.txt"
        try:
            (self.run_dir / fname).write_text(text or "", encoding="utf-8")
            self._index.append({"artifact": fname, "kind": "text"})
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to record %s: %s", fname, exc)

    # --- LLM call artifacts ---------------------------------------------------------

    def save_llm_call(
        self,
        step: str,
        input_messages: Any,
        output: str,
        usage: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist one LLM request/response pair, ordered by call sequence."""
        if not self.enabled:
            return
        with self._lock:
            self._llm_counter += 1
            idx = f"{self._llm_counter:02d}"
        base = f"{idx}_{_slug(step)}"
        try:
            (self.llm_dir / f"{base}.input.json").write_text(
                _safe_json({"step": step, "messages": input_messages, "usage": usage}),
                encoding="utf-8",
            )
            (self.llm_dir / f"{base}.output.txt").write_text(output or "", encoding="utf-8")
            self._index.append(
                {"artifact": f"llm/{base}", "kind": "llm", "step": step, "usage": usage}
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to record LLM call %s: %s", base, exc)

    # --- finalize -------------------------------------------------------------------

    def write_manifest(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        if not self.enabled:
            return
        manifest = {
            "created": datetime.now().isoformat(timespec="seconds"),
            "run_dir": str(self.run_dir),
            "llm_calls": self._llm_counter,
            "metadata": metadata or {},
            "artifacts": self._index,
        }
        try:
            (self.run_dir / "manifest.json").write_text(
                _safe_json(manifest), encoding="utf-8"
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to write manifest: %s", exc)
