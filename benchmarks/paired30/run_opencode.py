"""Launch paired-30 OpenCode runs with isolated sandboxes and resumable records."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import random
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmarks.paired30 import benchmark


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


@dataclass(frozen=True)
class Job:
    case_id: str
    condition: str
    repetition: int

    @property
    def run_id(self) -> str:
        return f"r{self.repetition}-{self.case_id}-{self.condition}"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _prepare_sandbox(job: Job, run_dir: Path, harness_root: Path = REPO) -> None:
    run_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(ROOT / "benchmark.py", run_dir / "benchmark.py")
    selected = benchmark._case(job.case_id)
    _write_json(run_dir / "cases.json", [selected])
    config = {
        "$schema": "https://opencode.ai/config.json",
        "permission": {"external_directory": "deny", "webfetch": "deny", "edit": "deny"},
    }
    _write_json(run_dir / "opencode.json", config)
    if job.condition == "graph":
        shutil.copy2(harness_root / "AGENTS.md", run_dir / "AGENTS.md")
        for name in ("scripts", "causal_graph", "adapters"):
            shutil.copytree(harness_root / name, run_dir / name)


def _prompt(job: Job) -> str:
    shared = (
        f"Investigate paired-30 benchmark case {job.case_id}. Use only the sealed evidence "
        "broker in this working directory. First run `python3 benchmark.py prompt "
        f"{job.case_id}`; investigate only with its `search` and `read` commands. "
        "Do not read cases.json directly, access another directory, or use the live web. "
        "Identify every material root cause, trace each causal path to the symptom, test "
        "attractive alternatives, cite opaque evidence IDs, and return only one JSON "
        "object matching answer_contract."
    )
    if job.condition == "bare":
        return shared + " This is the bare-agent condition: do not use or imitate the causal-graph harness."
    return (
        "Read and follow AGENTS.md for the investigation, using the copied causal-graph "
        f"scripts with topic paired30-{job.case_id}-r{job.repetition}. " + shared
    )


def _events(stdout: str) -> list[dict[str, Any]]:
    parsed = []
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            parsed.append(value)
    return parsed


def _extract_answer(events: list[dict[str, Any]]) -> dict[str, Any]:
    texts = [
        event.get("part", {}).get("text", "")
        for event in events
        if event.get("type") == "text" and isinstance(event.get("part", {}).get("text"), str)
    ]
    candidates = list(reversed(texts)) + ["\n".join(texts)]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        cleaned = candidate.strip()
        if cleaned.startswith("```json") and cleaned.endswith("```"):
            cleaned = cleaned[7:-3].strip()
        elif cleaned.startswith("```") and cleaned.endswith("```"):
            cleaned = cleaned[3:-3].strip()
        try:
            value = json.loads(cleaned)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
        for index, character in enumerate(cleaned):
            if character != "{":
                continue
            try:
                value, _ = decoder.raw_decode(cleaned[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "root_event_ids" in value:
                return value
    raise ValueError("no answer JSON object found in OpenCode text events")


def _usage(events: list[dict[str, Any]]) -> dict[str, Any]:
    finishes = [event["part"] for event in events if event.get("type") == "step_finish"]
    return {
        "agent_steps": len(finishes),
        "input_tokens": sum(part.get("tokens", {}).get("input", 0) for part in finishes),
        "output_tokens": sum(part.get("tokens", {}).get("output", 0) for part in finishes),
        "reasoning_tokens": sum(part.get("tokens", {}).get("reasoning", 0) for part in finishes),
        "model_cost": round(sum(part.get("cost", 0.0) for part in finishes), 8),
        "session_id": next((event.get("sessionID") for event in events if event.get("sessionID")), None),
    }


def _trace_counts(path: Path) -> dict[str, int]:
    counts = {"search_calls": 0, "evidence_reads": 0}
    if not path.is_file():
        return counts
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("action") == "search":
            counts["search_calls"] += 1
        elif record.get("action") == "read":
            counts["evidence_reads"] += 1
    return counts


def _run(job: Job, output_root: Path, server: str, protocol: dict[str, Any], harness_root: Path) -> dict[str, Any]:
    run_dir = output_root / "sandboxes" / job.run_id
    record_path = output_root / "records" / f"{job.run_id}.json"
    if record_path.is_file():
        return benchmark._read_json(record_path)
    _prepare_sandbox(job, run_dir, harness_root)
    command = [
        "opencode", "run", "--attach", server, "--dir", str(run_dir),
        "--model", protocol["model"], "--agent", protocol["agent"],
        "--pure", "--format", "json", _prompt(job),
    ]
    started = datetime.now(timezone.utc).isoformat()
    before = time.monotonic()
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=protocol["limits"]["wall_time_seconds"],
        check=False,
    )
    elapsed = time.monotonic() - before
    events = _events(completed.stdout)
    (run_dir / "events.jsonl").write_text(completed.stdout, encoding="utf-8")
    (run_dir / "opencode.stderr").write_text(completed.stderr, encoding="utf-8")
    trace = _trace_counts(run_dir / "evidence_trace.jsonl")
    record: dict[str, Any] = {
        "run_id": job.run_id,
        "case_id": job.case_id,
        "condition": job.condition,
        "repetition": job.repetition,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "wall_time_seconds": round(elapsed, 3),
        "process_returncode": completed.returncode,
        **_usage(events),
        **trace,
    }
    violations = []
    if trace["search_calls"] > protocol["limits"]["search_calls"]:
        violations.append("search_call_limit")
    if trace["evidence_reads"] > protocol["limits"]["evidence_reads"]:
        violations.append("evidence_read_limit")
    try:
        answer = _extract_answer(events)
        record["answer"] = answer
        record["score"] = benchmark.score_answer(job.case_id, answer)
    except (ValueError, benchmark.BenchmarkError, KeyError) as exc:
        record["answer_error"] = str(exc)
    record["protocol_violations"] = violations
    record["valid"] = completed.returncode == 0 and "score" in record and not violations
    _write_json(record_path, record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--server", default="http://127.0.0.1:4097")
    parser.add_argument("--repetitions", default="1")
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--harness-root", type=Path, default=Path("/home/kt/zero"))
    args = parser.parse_args()
    protocol = benchmark._read_json(ROOT / "protocol.json")
    if not (args.harness_root / "AGENTS.md").is_file():
        parser.error(f"harness root lacks AGENTS.md: {args.harness_root}")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=args.harness_root, text=True,
        capture_output=True, check=True,
    ).stdout.strip()
    if not revision.startswith(protocol["treatment_git_revision"]):
        parser.error(
            f"harness revision {revision} does not match frozen treatment "
            f"{protocol['treatment_git_revision']}"
        )
    repetitions = [int(value) for value in args.repetitions.split(",")]
    cases = args.cases or protocol["case_ids"]
    unknown = sorted(set(cases) - set(protocol["case_ids"]))
    if unknown:
        parser.error(f"unknown cases: {unknown}")
    jobs = [Job(case_id, condition, repetition)
            for repetition in repetitions for case_id in cases for condition in ("bare", "graph")]
    random.Random(protocol["launch_seed"] + sum(repetitions)).shuffle(jobs)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "records").mkdir(exist_ok=True)
    manifest = {
        "protocol": protocol,
        "requested_repetitions": repetitions,
        "run_order": [job.run_id for job in jobs],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(args.output / "manifest.json", manifest)
    concurrency = args.concurrency or protocol["limits"]["parallel_runs"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        future_jobs = {
            pool.submit(_run, job, args.output, args.server, protocol, args.harness_root): job
            for job in jobs
        }
        for future in concurrent.futures.as_completed(future_jobs):
            job = future_jobs[future]
            try:
                record = future.result()
                state = "valid" if record.get("valid") else "INVALID"
                print(f"{job.run_id}: {state}", flush=True)
            except Exception as exc:  # preserve other runs and make launcher failure visible
                print(f"{job.run_id}: LAUNCH_ERROR: {exc}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
