"""
Generic Parallel Task Runner
============================
A reusable, class-based parallel processing framework built on Python threads.
Not tied to any specific use case — extend Task to run anything in parallel.

Usage (CLI):
    python parallel_runner.py --input-dir ./input_files --etltool powerbi
    python parallel_runner.py --input-dir ./input_files --etltool powerbi --workers 6

Usage (programmatic):
    runner = ParallelRunner(max_workers=4)
    runner.add_task(MyTask("task-1"))
    runner.add_task(MyTask("task-2"))
    results = runner.run()
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import threading
import zipfile
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(threadName)s] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Abstract Task
# ─────────────────────────────────────────────────────────────────────────────

class Task(ABC):
    """
    Abstract base class for any unit of parallelizable work.

    Subclass this and implement:
      - execute()    → do the work, return a result dict
      - on_complete() → called immediately when execute() succeeds (optional)
      - on_error()   → called if execute() raises (optional)
    """

    def __init__(self, task_id: str):
        self.task_id = task_id

    @abstractmethod
    def execute(self) -> Any:
        """Run the task. Must be thread-safe. Return any result."""
        ...

    def on_complete(self, result: Any) -> None:
        """
        Called immediately after execute() returns in the same thread.
        Override for post-completion work (e.g. notifications, chaining).
        Default: log success.
        """
        log.info("[%s] Completed successfully.", self.task_id)

    def on_error(self, error: Exception) -> None:
        """
        Called if execute() raises an exception.
        Default: log the error.
        """
        log.error("[%s] Failed: %s", self.task_id, error)


# ─────────────────────────────────────────────────────────────────────────────
# 2. ParallelRunner
# ─────────────────────────────────────────────────────────────────────────────

class ParallelRunner:
    """
    Executes a list of Task objects in parallel using a thread pool.

    Key behaviour:
    - on_complete() fires per thread AS SOON as that thread finishes —
      it does NOT wait for all threads to complete first.
    - Thread count is auto-detected from system config if not provided.
    - All tasks run independently; one failure does not stop others.
    """

    # External service caps — tune these to match your environment.
    # Too many concurrent Databricks connections → cluster throttling.
    # Too many concurrent LLM calls → 429 rate-limit errors + exponential backoff retries
    # which make each thread SLOWER than sequential. For LLM-heavy pipelines keep this low (2-3).
    _DATABRICKS_CONN_LIMIT = 10
    _LLM_API_LIMIT = 3

    def __init__(self, max_workers: int | None = None):
        """
        Args:
            max_workers: Thread count override. If None, auto-detected
                         from system config + service caps.
        """
        self._explicit_workers = max_workers
        self._tasks: list[Task] = []
        self._lock = threading.Lock()

    def add_task(self, task: Task) -> "ParallelRunner":
        """Add a task. Returns self for fluent chaining."""
        self._tasks.append(task)
        return self

    def _resolve_workers(self) -> int:
        """
        Determine thread count from system config and service constraints.

        Priority (tightest cap wins):
          1. Explicit --workers override (CLI / constructor)      → hard cap
          2. Number of tasks                                      → no idle threads
          3. LLM API concurrency limit                           → avoid 429s
          4. Databricks connection limit                         → avoid throttling
          5. Python I/O-bound heuristic: min(32, cpu_count + 4)  → ceiling
        """
        num_tasks = len(self._tasks)
        if num_tasks == 0:
            return 1

        cpu_count = os.cpu_count() or 1
        # I/O-bound heuristic — more threads than CPUs is fine since
        # threads spend most time waiting on network (Databricks / LLM APIs).
        io_bound_ceil = min(32, cpu_count + 4)

        auto = min(
            io_bound_ceil,
            num_tasks,
            self._DATABRICKS_CONN_LIMIT,
            self._LLM_API_LIMIT,
        )

        if self._explicit_workers is not None:
            # Explicit value respected but still capped at num_tasks
            workers = min(self._explicit_workers, num_tasks)
            log.info(
                "Workers: %d (explicit override; capped at num_tasks=%d)",
                workers, num_tasks,
            )
        else:
            workers = auto
            log.info(
                "Workers: %d  [cpu=%d, io_ceil=%d, tasks=%d, db_limit=%d, llm_limit=%d]",
                workers, cpu_count, io_bound_ceil, num_tasks,
                self._DATABRICKS_CONN_LIMIT, self._LLM_API_LIMIT,
            )

        return workers

    def run(self) -> dict[str, Any]:
        """
        Execute all tasks in parallel. Returns a summary dict:
          { task_id: {"status": "success"|"error", "result"|"error": ...} }

        on_complete() / on_error() fire inside each worker thread
        immediately when that task finishes — not after all tasks finish.
        """
        if not self._tasks:
            log.warning("No tasks to run.")
            return {}

        workers = self._resolve_workers()
        total = len(self._tasks)
        log.info("Starting %d task(s) with %d worker thread(s) ...", total, workers)

        results: dict[str, Any] = {}
        completed_count = 0
        batch_start = datetime.now()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_task = {
                executor.submit(self._run_task, task): task
                for task in self._tasks
            }

            # as_completed yields each future the moment its thread finishes.
            # This is what makes on_complete() fire per-thread, not at the end.
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                completed_count += 1
                elapsed = getattr(task, "_elapsed", None)
                elapsed_str = str(elapsed).split(".")[0] if elapsed else "n/a"   # HH:MM:SS

                try:
                    outcome = future.result()   # re-raises if execute() threw
                    results[task.task_id] = {
                        "status": "success",
                        "result": outcome,
                        "elapsed": elapsed,
                    }
                except Exception as e:
                    error_msg = str(e)
                    results[task.task_id] = {
                        "status": "error",
                        "error": error_msg,
                        "elapsed": elapsed,
                    }
                    log.error(
                        "Progress: %d/%d done  |  %s → ERROR  |  thread_time=%s  |  reason: %s",
                        completed_count, total, task.task_id, elapsed_str, error_msg,
                    )
                    continue

                log.info(
                    "Progress: %d/%d done  |  %s → SUCCESS  |  thread_time=%s",
                    completed_count, total, task.task_id, elapsed_str,
                )

        batch_elapsed = datetime.now() - batch_start
        success = sum(1 for v in results.values() if v["status"] == "success")
        log.info(
            "All tasks finished — %d succeeded, %d failed — total_wall_time=%s",
            success, total - success,
            str(batch_elapsed).split(".")[0],
        )
        # Attach batch timing to results for the caller (main) to use
        results["__batch_elapsed__"] = batch_elapsed
        return results

    @staticmethod
    def _run_task(task: Task) -> Any:
        """Runs inside a worker thread. Records elapsed time on the task, then calls on_complete / on_error."""
        t0 = datetime.now()
        try:
            result = task.execute()
            task._elapsed = datetime.now() - t0
            task.on_complete(result)
            return result
        except Exception as e:
            task._elapsed = datetime.now() - t0  # record even on failure
            task.on_error(e)
            raise  # re-raise so future.result() captures it


# ─────────────────────────────────────────────────────────────────────────────
# 3. PowerBIPipelineTask  (concrete implementation for this project)
# ─────────────────────────────────────────────────────────────────────────────

class PowerBIPipelineTask(Task):
    """
    Processes a single .pbix file through the full pipeline:
      extract → layout mapping → LLM agents → normalize → write to Databricks → dedup

    Each instance owns its own temp directory so threads never collide.
    Databricks write happens inside execute(), so results are pushed
    to the catalog immediately when this thread finishes — not at the end.
    """

    def __init__(self, pbix_path: str):
        super().__init__(task_id=Path(pbix_path).name)
        self.pbix_path = Path(pbix_path)

    def execute(self) -> dict:
        # Lazy imports — keeps the module importable without all deps installed.
        import zipfile as _zf
        from powerbi_extractor import extract_powerbi_model
        from layout_mapper import map_layout_to_datamodel
        from agents_powerbi import run_single_tenant_flow_processor as run_powerbi_flow
        from databricks_normalizer import normalize_powerbi
        from databricks_writer import write_to_databricks
        from databricks_dedup import run_dedup_check

        session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        # Sanitize filename: replace spaces, brackets, parens and other
        # special chars with underscores to avoid Windows path errors.
        safe_stem = re.sub(r"[^\w\-]", "_", self.pbix_path.stem)
        temp_dir = Path("extracted_files") / f"powerbi_batch_{session_id}_{safe_stem}"
        os.makedirs(temp_dir, exist_ok=True)  # os.makedirs is atomic on Windows; pathlib.mkdir has a race condition
        log.info("[%s] Temp dir: %s", self.task_id, temp_dir)

        try:
            # ── Step 1: Copy pbix to temp dir & unzip ────────────────────────
            pbix_copy = temp_dir / self.pbix_path.name
            shutil.copy2(self.pbix_path, pbix_copy)

            file_paths: list[str] = []
            with _zf.ZipFile(pbix_copy) as zf:
                zf.extractall(temp_dir)
                file_paths = [str(temp_dir / n) for n in zf.namelist()
                              if (temp_dir / n).is_file()]

            log.info("[%s] Extracted %d files from .pbix", self.task_id, len(file_paths))

            # ── Step 2: Extract PowerBI model metadata ────────────────────────
            metadata_dir = temp_dir / "powerbi_metadata"
            start = datetime.now()
            extraction_result = extract_powerbi_model(
                pbix_path=str(pbix_copy),
                output_dir=str(metadata_dir),
            )
            log.info("[%s] Extraction done in %s", self.task_id, datetime.now() - start)

            # ── Step 3: Layout → data model mapping ──────────────────────────
            layout_file = next(
                (fp for fp in file_paths if "Report/Layout" in fp or fp.endswith("/Layout")),
                None,
            )
            mapping_result = None
            mapping_output_path = metadata_dir / "layout_datamodel_mapping.json"

            if layout_file:
                log.info("[%s] Layout file found: %s", self.task_id, layout_file)
                try:
                    start = datetime.now()
                    mapping_result = map_layout_to_datamodel(
                        layout_path=layout_file,
                        datamodel_folder=str(metadata_dir),
                        output_path=str(mapping_output_path),
                    )
                    log.info("[%s] Layout mapping done in %s", self.task_id, datetime.now() - start)
                except Exception as e:
                    log.warning("[%s] Layout mapping failed: %s", self.task_id, e)
                    mapping_result = {"error": str(e)}
            else:
                log.warning("[%s] No Layout file found.", self.task_id)

            # ── Step 4: LLM agent processing (async → run in this thread's loop)
            log.info("[%s] Starting LLM agent processing ...", self.task_id)
            start = datetime.now()
            # asyncio.run() creates a fresh event loop per thread — safe for threading.
            agent_result = asyncio.run(
                run_powerbi_flow(
                    extracted_metadata_folder=str(metadata_dir),
                )
            )
            log.info("[%s] Agent processing done in %s", self.task_id, datetime.now() - start)

            powerbi_response = {
                "status": "success",
                "message": f"PowerBI file processed successfully: {self.pbix_path.name}",
                "extraction_result": extraction_result,
                "mapping_result": mapping_result,
                "agent_result": agent_result,
            }

            # ── Step 5: Normalize & write to Databricks ───────────────────────
            log.info("[%s] Normalizing output ...", self.task_id)
            normalized = normalize_powerbi(powerbi_response, self.pbix_path.name)

            log.info("[%s] Writing to Databricks ...", self.task_id)
            start = datetime.now()
            db_summary = write_to_databricks(normalized)
            log.info("[%s] Databricks write done in %s — stored=%s",
                     self.task_id, datetime.now() - start, db_summary.get("stored"))

            # ── Step 6: Dedup check ───────────────────────────────────────────
            dedup_result: dict = {}
            if db_summary.get("stored"):
                try:
                    log.info("[%s] Running dedup check ...", self.task_id)
                    dedup_result = run_dedup_check()
                    log.info("[%s] Dedup: %s", self.task_id, dedup_result.get("summary"))
                except Exception as e:
                    log.warning("[%s] Dedup check failed: %s", self.task_id, e)
                    dedup_result = {"error": str(e)}

            powerbi_response["databricks_storage"] = db_summary
            powerbi_response["dedup_result"] = dedup_result
            return powerbi_response

        finally:
            # Always clean up temp dir regardless of success/failure
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                log.info("[%s] Temp dir cleaned up.", self.task_id)

    def on_complete(self, result: dict) -> None:
        db = result.get("databricks_storage", {})
        stored = db.get("stored", False)
        row_counts = db.get("row_counts", {})
        total_rows = sum(row_counts.values())
        elapsed = getattr(self, "_elapsed", None)
        elapsed_str = str(elapsed).split(".")[0] if elapsed else "n/a"
        log.info(
            "[%s] Added to Databricks catalog — stored=%s, total_rows=%d, thread_time=%s",
            self.task_id, stored, total_rows, elapsed_str,
        )

    def on_error(self, error: Exception) -> None:
        log.error("[%s] Pipeline failed: %s", self.task_id, error, exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# 4. CLI Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def _scan_input_files(input_dir: str, extension: str = ".pbix") -> list[Path]:
    """Return all files with the given extension in input_dir."""
    directory = Path(input_dir)
    if not directory.is_dir():
        raise ValueError(f"Input directory not found: {input_dir}")
    files = sorted(directory.glob(f"*{extension}"))
    return files


def _build_runner(files: list[Path], etltool: str, workers: int | None) -> ParallelRunner:
    """Create a ParallelRunner populated with tasks for each file."""
    runner = ParallelRunner(max_workers=workers)

    for f in files:
        if etltool == "powerbi":
            runner.add_task(PowerBIPipelineTask(str(f)))
        else:
            raise ValueError(
                f"Unsupported etltool '{etltool}'. "
                "Extend this function to add new task types."
            )

    return runner


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Run multiple BI files in parallel through the processing pipeline."
    )
    parser.add_argument(
        "--input-dir",
        default="./input_files",
        help="Directory containing input files (default: ./input_files)",
    )
    parser.add_argument(
        "--etltool",
        default="powerbi",
        choices=["powerbi"],
        help="Pipeline type to run (default: powerbi)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help=(
            "Number of parallel worker threads. "
            "If omitted, auto-detected from system config and service limits."
        ),
    )
    parser.add_argument(
        "--ext",
        default=".pbix",
        help="File extension to scan for (default: .pbix)",
    )
    args = parser.parse_args()

    # Discover files
    files = _scan_input_files(args.input_dir, args.ext)
    if not files:
        log.warning("No %s files found in %s. Exiting.", args.ext, args.input_dir)
        return

    log.info("Found %d file(s) in '%s':", len(files), args.input_dir)
    for f in files:
        log.info("  - %s", f.name)

    # Build and run
    batch_start = datetime.now()
    runner = _build_runner(files, args.etltool, args.workers)
    results = runner.run()
    batch_elapsed = results.pop("__batch_elapsed__", datetime.now() - batch_start)

    # Per-thread timing table
    task_results = {tid: v for tid, v in results.items() if not tid.startswith("__")}
    success = [tid for tid, v in task_results.items() if v["status"] == "success"]
    failed  = [tid for tid, v in task_results.items() if v["status"] == "error"]

    print("\n" + "=" * 80)
    print(f"{'FILE':<45} {'STATUS':<10} {'THREAD TIME'}")
    print("-" * 80)
    for tid, v in task_results.items():
        elapsed = v.get("elapsed")
        elapsed_str = str(elapsed).split(".")[0] if elapsed else "n/a"
        status_str  = "OK" if v["status"] == "success" else "FAILED"
        print(f"  {tid:<43} {status_str:<10} {elapsed_str}")
        if v["status"] == "error":
            # Truncate long error messages for readability
            err = v.get("error", "unknown error")
            print(f"    ERROR: {err[:120]}{'...' if len(err) > 120 else ''}")
    print("-" * 80)
    print(f"  {'TOTAL WALL TIME (parallel):':<43} {'':10} {str(batch_elapsed).split('.')[0]}")
    print("=" * 80)
    print(f"  BATCH COMPLETE — {len(success)} succeeded, {len(failed)} failed")
    print("=" * 80)


if __name__ == "__main__":
    main()
