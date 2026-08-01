# Causal Graph Agent Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the causal-graph research harness specified in `docs/superpowers/specs/2026-08-01-causal-graph-agent-harness-design.md` — a fact/deduction graph plus a Bayesian-updated causal graph, mutated only through deterministic Python CLI scripts, with a falsification gate, evidence-independence tracking, and retraction propagation.

**Architecture:** A stdlib-only Python package (`causal_graph/`) holds schema, storage, Bayes math, graph traversal, and lifecycle logic. Thin CLI scripts in `scripts/` are the only way any driving agent (or human) mutates state. `adapters/` holds one real adapter (`CodebaseAdapter`) plus stub interfaces; web and human evidence are agent-mediated, registered via `add_evidence.py` directly. State lives as plain JSON/JSONL files per topic under `research/<topic>/graph/`.

**Tech Stack:** Python 3.10+, stdlib only (argparse, dataclasses, enum, json, fcntl, tempfile, uuid, time). `pytest` as the sole dev dependency.

## Global Constraints

- Python >= 3.10; core package (`causal_graph`, `adapters`) uses stdlib only — no third-party runtime dependencies. `pytest` is a dev-only dependency.
- Only facts and deductions are graph nodes; evidence is never a node (spec: Data model). Node references are type-prefixed strings: `"fact:<id>"` / `"deduction:<id>"`.
- Every state mutation goes through `causal_graph.storage.commit_mutation` — no script writes a graph JSON file directly.
- `audit_log.jsonl` is the append-first, authoritative record; the graph JSON snapshot files are derived and repairable from it (spec: Error handling).
- Every script acquires the per-topic lock (`causal_graph.lock.topic_lock`) before touching state; one writer at a time per topic.
- High-confidence threshold = `0.9` posterior; reversal margin = `2.0`x odds shift in the opposite direction from trend — both are named constants in `causal_graph/review.py` (spec left the threshold value unspecified; this plan fixes it at a documented default, consistent with the reversal margin default already in the spec).
- `human` and `external_web` are adapter *name* conventions used with `add_evidence.py --adapter ...`, not Python adapter classes (spec: Evidence adapters, updated).
- `InternalDBAdapter`, `ManualDocAdapter`, `ExperimentResultsAdapter` are interface-only stubs that raise `NotImplementedError` with a clear message — never silently no-op.
- Storage location: `research/<topic>/graph/{facts.json, evidence.json, deductions.json, causal_edges.json, audit_log.jsonl, pending_review.jsonl, _meta.json}`.

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `causal_graph/__init__.py`
- Create: `causal_graph/cli.py`
- Create: `adapters/__init__.py`
- Create: `tests/__init__.py`
- Test: `tests/test_sanity.py`

**Interfaces:**
- Produces: `causal_graph.cli.current_agent_id() -> str` — reads `CAUSAL_GRAPH_AGENT_ID` env var, defaults to `"agent"`. Every later script uses this to tag `created_by`/`agent_id` fields.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "causal-graph-harness"
version = "0.1.0"
requires-python = ">=3.10"

[tool.setuptools]
packages = ["causal_graph", "adapters"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create empty package `__init__.py` files**

```bash
mkdir -p causal_graph adapters tests scripts
touch causal_graph/__init__.py adapters/__init__.py tests/__init__.py
```

- [ ] **Step 3: Write `causal_graph/cli.py`**

```python
import os


def current_agent_id() -> str:
    return os.environ.get("CAUSAL_GRAPH_AGENT_ID", "agent")
```

- [ ] **Step 4: Write the sanity test**

```python
# tests/test_sanity.py
from causal_graph.cli import current_agent_id


def test_current_agent_id_defaults(monkeypatch):
    monkeypatch.delenv("CAUSAL_GRAPH_AGENT_ID", raising=False)
    assert current_agent_id() == "agent"


def test_current_agent_id_from_env(monkeypatch):
    monkeypatch.setenv("CAUSAL_GRAPH_AGENT_ID", "custom")
    assert current_agent_id() == "custom"
```

- [ ] **Step 5: Install and run**

```bash
pip install -e . && pip install pytest
pytest tests/test_sanity.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml causal_graph adapters tests scripts
git commit -m "Scaffold causal-graph-harness package"
```

---

### Task 2: Schema & validation primitives

**Files:**
- Create: `causal_graph/schema.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Consumes: nothing (foundational module).
- Produces: `ValidationError(Exception)`; `Confidence` enum (`verified`/`reported`/`inferred`); `Status` enum (`active`/`contested`/`superseded`/`retracted`/`stale`); `new_id(prefix: str) -> str`; `parse_node_ref(ref: str) -> tuple[str, str]` (raises `ValidationError` on bad format); `validate_probability(value, name="value") -> float`; `validate_likelihood_ratio(value) -> float`. All later tasks import these.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_schema.py
import pytest
from causal_graph.schema import (
    ValidationError, Confidence, Status, new_id, parse_node_ref,
    validate_probability, validate_likelihood_ratio,
)


def test_new_id_has_prefix():
    assert new_id("fact").startswith("fact_")


def test_parse_node_ref_fact():
    assert parse_node_ref("fact:f1") == ("fact", "f1")


def test_parse_node_ref_deduction():
    assert parse_node_ref("deduction:d1") == ("deduction", "d1")


def test_parse_node_ref_rejects_bad_format():
    with pytest.raises(ValidationError):
        parse_node_ref("f1")
    with pytest.raises(ValidationError):
        parse_node_ref("evidence:e1")


def test_validate_probability_accepts_bounds():
    assert validate_probability(0.0) == 0.0
    assert validate_probability(1.0) == 1.0
    assert validate_probability(0.5) == 0.5


def test_validate_probability_rejects_out_of_bounds():
    with pytest.raises(ValidationError):
        validate_probability(1.5)
    with pytest.raises(ValidationError):
        validate_probability(-0.1)


def test_validate_likelihood_ratio_rejects_non_positive():
    with pytest.raises(ValidationError):
        validate_likelihood_ratio(0)
    with pytest.raises(ValidationError):
        validate_likelihood_ratio(-2.0)


def test_confidence_and_status_values():
    assert Confidence.VERIFIED.value == "verified"
    assert Status.STALE.value == "stale"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_schema.py -v
```
Expected: FAIL with `ModuleNotFoundError` / `ImportError`.

- [ ] **Step 3: Implement `causal_graph/schema.py`**

```python
from __future__ import annotations

import re
import uuid
from enum import Enum


class ValidationError(Exception):
    pass


class Confidence(str, Enum):
    VERIFIED = "verified"
    REPORTED = "reported"
    INFERRED = "inferred"


class Status(str, Enum):
    ACTIVE = "active"
    CONTESTED = "contested"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"
    STALE = "stale"


_NODE_REF_RE = re.compile(r"^(fact|deduction):(.+)$")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def parse_node_ref(ref: str) -> tuple[str, str]:
    m = _NODE_REF_RE.match(ref)
    if not m:
        raise ValidationError(
            f"invalid node reference: {ref!r} (expected 'fact:<id>' or 'deduction:<id>')"
        )
    return m.group(1), m.group(2)


def validate_probability(value, name: str = "value") -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValidationError(f"{name} must be a number, got {type(value).__name__}")
    if not (0.0 <= value <= 1.0):
        raise ValidationError(f"{name} must be in [0,1], got {value}")
    return float(value)


def validate_likelihood_ratio(value) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValidationError(f"likelihood_ratio must be a number, got {type(value).__name__}")
    if value <= 0:
        raise ValidationError(f"likelihood_ratio must be > 0, got {value}")
    return float(value)
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/test_schema.py -v
```
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add causal_graph/schema.py tests/test_schema.py
git commit -m "Add schema validation primitives"
```

---

### Task 3: Topic paths & per-topic lock

**Files:**
- Create: `causal_graph/topic.py`
- Create: `causal_graph/lock.py`
- Test: `tests/test_topic_lock.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `causal_graph.topic.FILES: dict[str,str]` (keys: `facts`, `evidence`, `deductions`, `causal_edges`, `audit_log`, `pending_review`, `meta`); `graph_dir(topic: str) -> Path`; `ensure_graph_dir(topic: str) -> Path`; `path_for(topic: str, key: str) -> Path`. `causal_graph.lock.topic_lock(topic: str)` — context manager, exclusive per-topic file lock via `fcntl.flock`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_topic_lock.py
import time
from pathlib import Path

from causal_graph.topic import graph_dir, ensure_graph_dir, path_for
from causal_graph.lock import topic_lock


def test_graph_dir_layout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = ensure_graph_dir("my-topic")
    assert d == Path("research/my-topic/graph")
    assert d.is_dir()


def test_path_for_known_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert path_for("t", "facts").name == "facts.json"
    assert path_for("t", "audit_log").name == "audit_log.jsonl"


def test_topic_lock_is_exclusive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    order = []
    with topic_lock("t"):
        order.append("first-acquired")
    with topic_lock("t"):
        order.append("second-acquired")
    assert order == ["first-acquired", "second-acquired"]
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_topic_lock.py -v
```
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `causal_graph/topic.py`**

```python
from pathlib import Path

FILES = {
    "facts": "facts.json",
    "evidence": "evidence.json",
    "deductions": "deductions.json",
    "causal_edges": "causal_edges.json",
    "audit_log": "audit_log.jsonl",
    "pending_review": "pending_review.jsonl",
    "meta": "_meta.json",
}


def graph_dir(topic: str) -> Path:
    return Path("research") / topic / "graph"


def ensure_graph_dir(topic: str) -> Path:
    d = graph_dir(topic)
    d.mkdir(parents=True, exist_ok=True)
    return d


def path_for(topic: str, key: str) -> Path:
    return graph_dir(topic) / FILES[key]
```

- [ ] **Step 4: Implement `causal_graph/lock.py`**

```python
import contextlib
import fcntl

from .topic import ensure_graph_dir


@contextlib.contextmanager
def topic_lock(topic: str):
    d = ensure_graph_dir(topic)
    lock_path = d / ".lock"
    with open(lock_path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
```

- [ ] **Step 5: Run to verify pass**

```bash
pytest tests/test_topic_lock.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add causal_graph/topic.py causal_graph/lock.py tests/test_topic_lock.py
git commit -m "Add topic path resolution and per-topic file lock"
```

---

### Task 4: Storage layer — audit-log-first commit, snapshots, repair

**Files:**
- Create: `causal_graph/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: `causal_graph.topic.{path_for, ensure_graph_dir}`.
- Produces: `load_json_list(topic, key) -> list[dict]`; `save_json_list(topic, key, records) -> None`; `upsert(topic, key, record) -> None` (record with `record["_delete"] = True` removes by `id` instead); `append_audit(topic, entry) -> None`; `read_audit(topic) -> list[dict]`; `commit_mutation(topic, agent_id, script, args, writes: list[tuple[str, dict]]) -> dict` (appends one audit entry recording all writes, then applies each write via `upsert`, then advances the meta pointer; returns the audit entry); `prepare(topic) -> None` (ensures dir exists and repairs any unapplied audit entries); `repair(topic) -> int` (returns count of entries repaired).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storage.py
import json

from causal_graph import storage
from causal_graph.topic import path_for


def test_upsert_inserts_and_updates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage.upsert("t", "facts", {"id": "f1", "statement": "a"})
    storage.upsert("t", "facts", {"id": "f1", "statement": "b"})
    records = storage.load_json_list("t", "facts")
    assert records == [{"id": "f1", "statement": "b"}]


def test_upsert_delete(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage.upsert("t", "facts", {"id": "f1", "statement": "a"})
    storage.upsert("t", "facts", {"id": "f1", "_delete": True})
    assert storage.load_json_list("t", "facts") == []


def test_commit_mutation_writes_audit_and_snapshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    entry = storage.commit_mutation(
        "t", "agent-1", "add_fact.py", {"statement": "x"},
        [("facts", {"id": "f1", "statement": "x"})],
    )
    assert entry["agent_id"] == "agent-1"
    assert entry["script"] == "add_fact.py"
    assert storage.load_json_list("t", "facts") == [{"id": "f1", "statement": "x"}]
    audit = storage.read_audit("t")
    assert len(audit) == 1
    assert audit[0]["result"]["writes"][0]["record"]["id"] == "f1"


def test_repair_replays_unapplied_audit_entries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage.commit_mutation(
        "t", "agent-1", "add_fact.py", {}, [("facts", {"id": "f1", "statement": "x"})],
    )
    # Simulate a crash: audit entry exists but snapshot was never written and
    # the meta pointer was never advanced.
    storage.save_json_list("t", "facts", [])
    meta_path = path_for("t", "meta")
    meta = json.loads(meta_path.read_text())
    meta["applied_through"] = 0
    meta_path.write_text(json.dumps(meta))

    repaired = storage.repair("t")

    assert repaired == 1
    assert storage.load_json_list("t", "facts") == [{"id": "f1", "statement": "x"}]


def test_prepare_creates_dir_and_repairs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage.prepare("t")
    assert path_for("t", "facts").parent.is_dir()
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_storage.py -v
```
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `causal_graph/storage.py`**

```python
import json
import os
import tempfile
import time

from .topic import ensure_graph_dir, path_for


def _atomic_write(path, data) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_json_list(topic: str, key: str) -> list:
    p = path_for(topic, key)
    if not p.exists():
        return []
    with open(p) as f:
        return json.load(f)


def save_json_list(topic: str, key: str, records: list) -> None:
    ensure_graph_dir(topic)
    _atomic_write(path_for(topic, key), records)


def upsert(topic: str, key: str, record: dict) -> None:
    records = load_json_list(topic, key)
    if record.get("_delete"):
        records = [r for r in records if r["id"] != record["id"]]
        save_json_list(topic, key, records)
        return
    for i, r in enumerate(records):
        if r["id"] == record["id"]:
            records[i] = record
            break
    else:
        records.append(record)
    save_json_list(topic, key, records)


def append_audit(topic: str, entry: dict) -> None:
    ensure_graph_dir(topic)
    p = path_for(topic, "audit_log")
    with open(p, "a") as f:
        f.write(json.dumps(entry) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_audit(topic: str) -> list:
    p = path_for(topic, "audit_log")
    if not p.exists():
        return []
    with open(p) as f:
        return [json.loads(line) for line in f if line.strip()]


def _load_meta(topic: str) -> dict:
    p = path_for(topic, "meta")
    if not p.exists():
        return {"applied_through": 0}
    with open(p) as f:
        return json.load(f)


def _save_meta(topic: str, meta: dict) -> None:
    ensure_graph_dir(topic)
    _atomic_write(path_for(topic, "meta"), meta)


def commit_mutation(topic: str, agent_id: str, script: str, args: dict,
                     writes: list) -> dict:
    ensure_graph_dir(topic)
    entry = {
        "timestamp": time.time(),
        "agent_id": agent_id,
        "script": script,
        "args": args,
        "result": {"writes": [{"file": key, "record": record} for key, record in writes]},
    }
    append_audit(topic, entry)
    for key, record in writes:
        upsert(topic, key, record)
    meta = _load_meta(topic)
    meta["applied_through"] = len(read_audit(topic))
    _save_meta(topic, meta)
    return entry


def repair(topic: str) -> int:
    meta = _load_meta(topic)
    entries = read_audit(topic)
    applied = meta.get("applied_through", 0)
    pending = entries[applied:]
    for entry in pending:
        for w in entry["result"]["writes"]:
            upsert(topic, w["file"], w["record"])
    meta["applied_through"] = len(entries)
    _save_meta(topic, meta)
    return len(pending)


def prepare(topic: str) -> None:
    ensure_graph_dir(topic)
    repair(topic)
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/test_storage.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add causal_graph/storage.py tests/test_storage.py
git commit -m "Add audit-log-first storage layer with crash repair"
```

---

### Task 5: Bayesian update math

**Files:**
- Create: `causal_graph/bayes.py`
- Test: `tests/test_bayes.py`

**Interfaces:**
- Consumes: nothing (pure math module).
- Produces: `posterior_from_odds(prior: float, likelihood_ratio: float) -> float`; `group_correlated(updates: list[dict]) -> list[list[dict]]` (each update dict has `evidence_id`, `likelihood_ratio`, `correlated_with: list[str]`); `compute_posterior(prior: float, updates: list[dict]) -> float`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bayes.py
import math

from causal_graph.bayes import posterior_from_odds, group_correlated, compute_posterior


def test_posterior_from_odds_hand_computed():
    # prior odds = 0.3/0.7; new_odds = odds * 4; posterior = new_odds/(1+new_odds)
    prior = 0.3
    lr = 4.0
    odds = prior / (1 - prior)
    expected = (odds * lr) / (1 + odds * lr)
    assert math.isclose(posterior_from_odds(prior, lr), expected, rel_tol=1e-9)


def test_posterior_from_odds_bounds():
    assert posterior_from_odds(0.0, 5.0) == 0.0
    assert posterior_from_odds(1.0, 0.1) == 1.0


def test_group_correlated_independent_by_default():
    updates = [
        {"evidence_id": "e1", "likelihood_ratio": 2.0, "correlated_with": []},
        {"evidence_id": "e2", "likelihood_ratio": 3.0, "correlated_with": []},
    ]
    groups = group_correlated(updates)
    assert sorted(len(g) for g in groups) == [1, 1]


def test_group_correlated_links_via_correlated_with():
    updates = [
        {"evidence_id": "e1", "likelihood_ratio": 2.0, "correlated_with": []},
        {"evidence_id": "e2", "likelihood_ratio": 3.0, "correlated_with": ["e1"]},
    ]
    groups = group_correlated(updates)
    assert len(groups) == 1
    assert len(groups[0]) == 2


def test_compute_posterior_independent_evidence_multiplies():
    prior = 0.3
    updates = [
        {"evidence_id": "e1", "likelihood_ratio": 2.0, "correlated_with": []},
        {"evidence_id": "e2", "likelihood_ratio": 3.0, "correlated_with": []},
    ]
    result = compute_posterior(prior, updates)
    expected = posterior_from_odds(posterior_from_odds(prior, 2.0), 3.0)
    assert math.isclose(result, expected, rel_tol=1e-9)


def test_compute_posterior_correlated_evidence_does_not_double_count():
    prior = 0.3
    independent_only = compute_posterior(
        prior, [{"evidence_id": "e1", "likelihood_ratio": 8.0, "correlated_with": []}]
    )
    correlated_pair = compute_posterior(
        prior,
        [
            {"evidence_id": "e1", "likelihood_ratio": 8.0, "correlated_with": []},
            {"evidence_id": "e2", "likelihood_ratio": 5.0, "correlated_with": ["e1"]},
        ],
    )
    # Correlated group uses the strongest single LR (8.0), not the product (40.0),
    # so it must equal applying 8.0 alone, not exceed it.
    assert math.isclose(correlated_pair, independent_only, rel_tol=1e-9)
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_bayes.py -v
```
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `causal_graph/bayes.py`**

```python
def posterior_from_odds(prior: float, likelihood_ratio: float) -> float:
    if prior <= 0.0:
        return 0.0
    if prior >= 1.0:
        return 1.0
    odds = prior / (1 - prior)
    new_odds = odds * likelihood_ratio
    return new_odds / (1 + new_odds)


def _find(parent: dict, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _union(parent: dict, a, b) -> None:
    ra, rb = _find(parent, a), _find(parent, b)
    if ra != rb:
        parent[ra] = rb


def group_correlated(updates: list) -> list:
    ids = [u["evidence_id"] for u in updates]
    parent = {i: i for i in ids}
    by_id = {u["evidence_id"]: u for u in updates}
    for u in updates:
        for other in u.get("correlated_with", []):
            if other in parent:
                _union(parent, u["evidence_id"], other)
    groups: dict = {}
    for i in ids:
        root = _find(parent, i)
        groups.setdefault(root, []).append(by_id[i])
    return list(groups.values())


def compute_posterior(prior: float, updates: list) -> float:
    posterior = prior
    for group in group_correlated(updates):
        effective_lr = max(u["likelihood_ratio"] for u in group)
        posterior = posterior_from_odds(posterior, effective_lr)
    return posterior
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/test_bayes.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add causal_graph/bayes.py tests/test_bayes.py
git commit -m "Add Bayesian posterior math with correlated-evidence grouping"
```

---

### Task 6: Graph traversal — downstream dependents & urgency tiering

**Files:**
- Create: `causal_graph/graph.py`
- Test: `tests/test_graph.py`

**Interfaces:**
- Consumes: `causal_graph.storage.load_json_list`; `causal_graph.schema.parse_node_ref`.
- Produces: `downstream_dependents(topic: str, node_ref: str) -> set[str]` (returns refs like `"deduction:d1"`, `"edge:e1"` of everything transitively depending on `node_ref`); `urgency_tier(topic: str, node_ref: str) -> str` (`"urgent"` or `"normal"`; below 8 total fact+deduction nodes always `"normal"`; otherwise top-10th-percentile by dependent count is `"urgent"`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_graph.py
from causal_graph import storage
from causal_graph.graph import downstream_dependents, urgency_tier


def _seed_small_chain(topic):
    storage.save_json_list(topic, "facts", [{"id": "f1"}, {"id": "f2"}])
    storage.save_json_list(topic, "deductions", [
        {"id": "d1", "supporting_fact_ids": ["f1"], "supporting_deduction_ids": []},
    ])
    storage.save_json_list(topic, "causal_edges", [
        {"id": "e1", "from_node": "deduction:d1", "to_node": "fact:f2"},
    ])


def test_downstream_dependents_chain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_small_chain("t")
    deps = downstream_dependents("t", "fact:f1")
    assert deps == {"deduction:d1", "edge:e1"}


def test_downstream_dependents_leaf_has_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_small_chain("t")
    assert downstream_dependents("t", "fact:f2") == set()


def test_urgency_tier_below_floor_is_always_normal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_small_chain("t")  # only 3 fact/deduction nodes, well below the 8-node floor
    assert urgency_tier("t", "fact:f1") == "normal"


def test_urgency_tier_above_floor_flags_high_impact_node(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    facts = [{"id": f"f{i}"} for i in range(10)]
    storage.save_json_list("t", "facts", facts)
    # d1 depends on every fact; the rest are independent leaves.
    deductions = [{"id": "d1", "supporting_fact_ids": [f["id"] for f in facts], "supporting_deduction_ids": []}]
    storage.save_json_list("t", "deductions", deductions)
    storage.save_json_list("t", "causal_edges", [])
    assert urgency_tier("t", "fact:f0") == "urgent"
    assert urgency_tier("t", "deduction:d1") == "normal"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_graph.py -v
```
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `causal_graph/graph.py`**

```python
from .schema import parse_node_ref


def _load_maps(topic: str):
    from . import storage
    facts = {f["id"]: f for f in storage.load_json_list(topic, "facts")}
    deductions = {d["id"]: d for d in storage.load_json_list(topic, "deductions")}
    edges = storage.load_json_list(topic, "causal_edges")
    return facts, deductions, edges


def downstream_dependents(topic: str, node_ref: str) -> set:
    facts, deductions, edges = _load_maps(topic)
    parse_node_ref(node_ref)  # validates format, raises ValidationError if malformed
    dependents: set = set()
    frontier = {node_ref}
    changed = True
    while changed:
        changed = False
        known = frontier | dependents
        for d in deductions.values():
            dref = f"deduction:{d['id']}"
            if dref in dependents:
                continue
            supports = {f"fact:{i}" for i in d.get("supporting_fact_ids", [])} | \
                       {f"deduction:{i}" for i in d.get("supporting_deduction_ids", [])}
            if supports & known:
                dependents.add(dref)
                frontier.add(dref)
                changed = True
        known = frontier | dependents
        for e in edges:
            eref = f"edge:{e['id']}"
            if eref in dependents:
                continue
            if e["from_node"] in known:
                dependents.add(eref)
                frontier.add(eref)
                changed = True
    return dependents


def urgency_tier(topic: str, node_ref: str) -> str:
    facts, deductions, edges = _load_maps(topic)
    total_nodes = len(facts) + len(deductions)
    if total_nodes < 8:
        return "normal"
    all_refs = [f"fact:{i}" for i in facts] + [f"deduction:{i}" for i in deductions]
    counts = sorted(len(downstream_dependents(topic, r)) for r in all_refs)
    my_count = len(downstream_dependents(topic, node_ref))
    rank = sum(1 for c in counts if c <= my_count) / len(counts)
    return "urgent" if rank >= 0.9 else "normal"
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/test_graph.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add causal_graph/graph.py tests/test_graph.py
git commit -m "Add downstream-dependency traversal and relative urgency tiering"
```

---

### Task 7: `add_evidence.py`

**Files:**
- Create: `scripts/add_evidence.py`
- Test: `tests/test_add_evidence.py`

**Interfaces:**
- Consumes: `causal_graph.storage.{prepare, commit_mutation}`; `causal_graph.lock.topic_lock`; `causal_graph.schema.new_id`; `causal_graph.cli.current_agent_id`.
- Produces: CLI `add_evidence.py --topic T --adapter NAME --content TEXT --source-ref REF`; prints the new evidence id to stdout; writes one record to `evidence.json` with keys `{id, content, source_adapter, source_ref, retrieved_at}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_add_evidence.py
import subprocess
import sys

from causal_graph import storage


def _run(args, cwd):
    return subprocess.run(
        [sys.executable, "scripts/add_evidence.py", *args],
        cwd=cwd, capture_output=True, text=True,
    )


def test_add_evidence_writes_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "scripts").mkdir()
    import shutil, pathlib
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    shutil.copy(repo_root / "scripts" / "add_evidence.py", tmp_path / "scripts" / "add_evidence.py")

    result = _run(
        ["--topic", "t", "--adapter", "human", "--content", "saw it happen",
         "--source-ref", "conversation:2026-08-01"],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    ev_id = result.stdout.strip()
    records = storage.load_json_list("t", "evidence")
    assert len(records) == 1
    assert records[0]["id"] == ev_id
    assert records[0]["source_adapter"] == "human"
    assert records[0]["content"] == "saw it happen"
```

> Note: this test copies the script into an isolated `tmp_path` and runs it as a subprocess against that directory so it exercises the real CLI end-to-end without touching the repo's own `research/` folder. Every later CLI test in this plan follows the same pattern.

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_add_evidence.py -v
```
Expected: FAIL (`scripts/add_evidence.py` does not exist yet, non-zero exit).

- [ ] **Step 3: Implement `scripts/add_evidence.py`**

```python
#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from causal_graph import storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--adapter", required=True)
    p.add_argument("--content", required=True)
    p.add_argument("--source-ref", required=True, dest="source_ref")
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        record = {
            "id": new_id("ev"),
            "content": args.content,
            "source_adapter": args.adapter,
            "source_ref": args.source_ref,
            "retrieved_at": time.time(),
        }
        storage.commit_mutation(
            args.topic, current_agent_id(), "add_evidence.py", vars(args),
            [("evidence", record)],
        )
    print(record["id"])


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/test_add_evidence.py -v
```
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/add_evidence.py tests/test_add_evidence.py
git commit -m "Add add_evidence.py CLI script"
```

---

### Task 8: `add_fact.py` (with contradiction flagging)

**Files:**
- Create: `scripts/add_fact.py`
- Test: `tests/test_add_fact.py`

**Interfaces:**
- Consumes: same as Task 7, plus `causal_graph.schema.Confidence`.
- Produces: CLI `add_fact.py --topic T --statement TEXT --evidence-id ID [--evidence-id ID ...] --confidence {verified|reported|inferred} [--contradicts FACT_ID]`. Writes to `facts.json`: `{id, statement, evidence_ids, confidence, status: "active", supersedes_id: null, created_at, created_by}`. If `--contradicts` is given, also writes a `pending_review` item of `kind: "contradiction"` instead of leaving the fact unflagged — this is the "two facts/deductions are structurally contradictory" review trigger from the spec; the fact is still added (status active), but flagged for human/agent review since only the caller can recognize semantic contradiction, and the script's job is to force it into review rather than let it pass silently.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_add_fact.py
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("add_evidence.py", "add_fact.py"):
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )


def test_add_fact_requires_known_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    result = _run("add_fact.py", [
        "--topic", "t", "--statement", "x", "--evidence-id", "missing",
        "--confidence", "verified",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "unknown evidence id" in result.stderr


def test_add_fact_writes_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", [
        "--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r",
    ], cwd=tmp_path).stdout.strip()

    result = _run("add_fact.py", [
        "--topic", "t", "--statement", "OOM killed the job", "--evidence-id", ev,
        "--confidence", "verified",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    fact_id = result.stdout.strip()
    facts = storage.load_json_list("t", "facts")
    assert facts[0]["id"] == fact_id
    assert facts[0]["status"] == "active"
    assert facts[0]["evidence_ids"] == [ev]


def test_add_fact_with_contradicts_queues_review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", [
        "--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r",
    ], cwd=tmp_path).stdout.strip()
    first = _run("add_fact.py", [
        "--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "reported",
    ], cwd=tmp_path).stdout.strip()

    result = _run("add_fact.py", [
        "--topic", "t", "--statement", "not A", "--evidence-id", ev,
        "--confidence", "reported", "--contradicts", first,
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    pending = storage.load_json_list("t", "pending_review")
    assert len(pending) == 1
    assert pending[0]["kind"] == "contradiction"
    assert pending[0]["contradicts_fact_id"] == first
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_add_fact.py -v
```
Expected: FAIL (`scripts/add_fact.py` does not exist yet).

- [ ] **Step 3: Implement `scripts/add_fact.py`**

```python
#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from causal_graph import storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import Confidence, ValidationError, new_id


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--statement", required=True)
    p.add_argument("--evidence-id", action="append", required=True, dest="evidence_ids")
    p.add_argument("--confidence", required=True, choices=[c.value for c in Confidence])
    p.add_argument("--contradicts", default=None, help="ID of an existing fact this contradicts")
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        known_evidence = {e["id"] for e in storage.load_json_list(args.topic, "evidence")}
        missing = [eid for eid in args.evidence_ids if eid not in known_evidence]
        if missing:
            raise ValidationError(f"unknown evidence id(s): {missing}")

        record = {
            "id": new_id("fact"),
            "statement": args.statement,
            "evidence_ids": args.evidence_ids,
            "confidence": args.confidence,
            "status": "active",
            "supersedes_id": None,
            "created_at": time.time(),
            "created_by": current_agent_id(),
        }
        writes = [("facts", record)]

        if args.contradicts:
            known_facts = {f["id"] for f in storage.load_json_list(args.topic, "facts")}
            if args.contradicts not in known_facts:
                raise ValidationError(f"unknown contradicts target: {args.contradicts}")
            writes.append(("pending_review", {
                "id": new_id("rev"),
                "kind": "contradiction",
                "fact_id": record["id"],
                "contradicts_fact_id": args.contradicts,
                "reason": f"flagged as contradicting {args.contradicts}",
                "tier": "normal",
                "created_at": time.time(),
            }))

        storage.commit_mutation(
            args.topic, current_agent_id(), "add_fact.py", vars(args), writes,
        )
    print(record["id"])


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/test_add_fact.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/add_fact.py tests/test_add_fact.py
git commit -m "Add add_fact.py CLI script with contradiction flagging"
```

---

### Task 9: `add_deduction.py`

**Files:**
- Create: `scripts/add_deduction.py`
- Test: `tests/test_add_deduction.py`

**Interfaces:**
- Consumes: `causal_graph.schema.parse_node_ref`, plus Task 7/8 patterns.
- Produces: CLI `add_deduction.py --topic T --claim TEXT --supports "fact:ID,deduction:ID2" [--logic-note TEXT]`. Writes to `deductions.json`: `{id, claim, supporting_fact_ids, supporting_deduction_ids, logic_note, status: "active", supersedes_id: null, created_at, created_by}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_add_deduction.py
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("add_evidence.py", "add_fact.py", "add_deduction.py"):
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )


def test_add_deduction_rejects_unknown_support(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    result = _run("add_deduction.py", [
        "--topic", "t", "--claim", "x", "--supports", "fact:missing",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "unknown supporting node" in result.stderr


def test_add_deduction_writes_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    f2 = _run("add_fact.py", ["--topic", "t", "--statement", "B", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()

    result = _run("add_deduction.py", [
        "--topic", "t", "--claim", "A and B together imply C",
        "--supports", f"fact:{f1},fact:{f2}", "--logic-note", "conjunction",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    ded_id = result.stdout.strip()
    deds = storage.load_json_list("t", "deductions")
    assert deds[0]["id"] == ded_id
    assert deds[0]["supporting_fact_ids"] == [f1, f2]
    assert deds[0]["status"] == "active"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_add_deduction.py -v
```
Expected: FAIL (`scripts/add_deduction.py` does not exist yet).

- [ ] **Step 3: Implement `scripts/add_deduction.py`**

```python
#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from causal_graph import storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id, parse_node_ref


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--claim", required=True)
    p.add_argument("--supports", required=True, help="comma-separated fact:ID/deduction:ID refs")
    p.add_argument("--logic-note", default="", dest="logic_note")
    args = p.parse_args()

    refs = [r.strip() for r in args.supports.split(",") if r.strip()]
    fact_ids, deduction_ids = [], []
    for r in refs:
        kind, rid = parse_node_ref(r)
        (fact_ids if kind == "fact" else deduction_ids).append(rid)

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        known_facts = {f["id"] for f in storage.load_json_list(args.topic, "facts")}
        known_deductions = {d["id"] for d in storage.load_json_list(args.topic, "deductions")}
        missing = [f"fact:{i}" for i in fact_ids if i not in known_facts] + \
                  [f"deduction:{i}" for i in deduction_ids if i not in known_deductions]
        if missing:
            raise ValidationError(f"unknown supporting node(s): {missing}")

        record = {
            "id": new_id("ded"),
            "claim": args.claim,
            "supporting_fact_ids": fact_ids,
            "supporting_deduction_ids": deduction_ids,
            "logic_note": args.logic_note,
            "status": "active",
            "supersedes_id": None,
            "created_at": time.time(),
            "created_by": current_agent_id(),
        }
        storage.commit_mutation(
            args.topic, current_agent_id(), "add_deduction.py", vars(args),
            [("deductions", record)],
        )
    print(record["id"])


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/test_add_deduction.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/add_deduction.py tests/test_add_deduction.py
git commit -m "Add add_deduction.py CLI script"
```

---

### Task 10: `propose_causal_edge.py`

**Files:**
- Create: `scripts/propose_causal_edge.py`
- Test: `tests/test_propose_causal_edge.py`

**Interfaces:**
- Consumes: `causal_graph.schema.{parse_node_ref, validate_probability}`.
- Produces: CLI `propose_causal_edge.py --topic T --from REF --to REF --relation-type TEXT --prior FLOAT`. Writes to `causal_edges.json`: `{id, from_node, to_node, relation_type, prior, posterior, status: "active", supersedes_id: null, updates: [], falsification_checks: [], last_updated}`. `posterior` starts equal to `prior`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_propose_causal_edge.py
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("add_evidence.py", "add_fact.py", "add_deduction.py", "propose_causal_edge.py"):
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )


def _seed_fact(tmp_path, statement):
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    return _run("add_fact.py", ["--topic", "t", "--statement", statement, "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()


def test_propose_causal_edge_rejects_unknown_node(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    f1 = _seed_fact(tmp_path, "A")
    result = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"fact:{f1}", "--to", "fact:missing",
        "--relation-type", "contributes-to", "--prior", "0.3",
    ], cwd=tmp_path)
    assert result.returncode != 0
    assert "unknown node reference" in result.stderr


def test_propose_causal_edge_writes_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    f1 = _seed_fact(tmp_path, "memory limit cut")
    f2 = _seed_fact(tmp_path, "job OOM-killed")

    result = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"fact:{f1}", "--to", f"fact:{f2}",
        "--relation-type", "contributes-to", "--prior", "0.3",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    edge_id = result.stdout.strip()
    edges = storage.load_json_list("t", "causal_edges")
    assert edges[0]["id"] == edge_id
    assert edges[0]["prior"] == 0.3
    assert edges[0]["posterior"] == 0.3
    assert edges[0]["updates"] == []
    assert edges[0]["falsification_checks"] == []
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_propose_causal_edge.py -v
```
Expected: FAIL (`scripts/propose_causal_edge.py` does not exist yet).

- [ ] **Step 3: Implement `scripts/propose_causal_edge.py`**

```python
#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from causal_graph import storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id, parse_node_ref, validate_probability


def _node_exists(topic: str, ref: str) -> bool:
    kind, rid = parse_node_ref(ref)
    key = "facts" if kind == "fact" else "deductions"
    return any(r["id"] == rid for r in storage.load_json_list(topic, key))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--from", required=True, dest="from_node")
    p.add_argument("--to", required=True, dest="to_node")
    p.add_argument("--relation-type", required=True, dest="relation_type")
    p.add_argument("--prior", required=True, type=float)
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        for ref in (args.from_node, args.to_node):
            if not _node_exists(args.topic, ref):
                raise ValidationError(f"unknown node reference: {ref}")
        prior = validate_probability(args.prior, "prior")
        record = {
            "id": new_id("edge"),
            "from_node": args.from_node,
            "to_node": args.to_node,
            "relation_type": args.relation_type,
            "prior": prior,
            "posterior": prior,
            "status": "active",
            "supersedes_id": None,
            "updates": [],
            "falsification_checks": [],
            "last_updated": time.time(),
        }
        storage.commit_mutation(
            args.topic, current_agent_id(), "propose_causal_edge.py", vars(args),
            [("causal_edges", record)],
        )
    print(record["id"])


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/test_propose_causal_edge.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/propose_causal_edge.py tests/test_propose_causal_edge.py
git commit -m "Add propose_causal_edge.py CLI script"
```

---

### Task 11: Review triggers + `update_causal_edge.py`

**Files:**
- Create: `causal_graph/review.py`
- Create: `scripts/update_causal_edge.py`
- Test: `tests/test_review.py`
- Test: `tests/test_update_causal_edge.py`

**Interfaces:**
- Consumes: `causal_graph.bayes.compute_posterior`; `causal_graph.storage`; `causal_graph.schema.{ValidationError, new_id, validate_likelihood_ratio}`.
- Produces: `causal_graph.review.{HIGH_CONFIDENCE_THRESHOLD, REVERSAL_ODDS_MULTIPLE, crosses_high_confidence(old, new) -> bool, is_reversal(prior, current, new) -> bool}`. CLI `update_causal_edge.py --topic T --edge-id ID --evidence-id ID --likelihood-ratio FLOAT [--correlated-with "id1,id2"]` — recomputes the trial posterior; if it crosses `HIGH_CONFIDENCE_THRESHOLD` with no `falsification_checks` recorded, or is a reversal per `is_reversal`, diverts to `pending_review` (`kind: "causal_edge_update"`) instead of applying; otherwise applies the update to `causal_edges.json`.

- [ ] **Step 1: Write the failing tests for `causal_graph/review.py`**

```python
# tests/test_review.py
from causal_graph.review import crosses_high_confidence, is_reversal, HIGH_CONFIDENCE_THRESHOLD


def test_crosses_high_confidence_true_when_moving_past_threshold():
    assert crosses_high_confidence(0.85, 0.95) is True


def test_crosses_high_confidence_false_when_already_above():
    assert crosses_high_confidence(0.95, 0.97) is False


def test_crosses_high_confidence_false_when_staying_below():
    assert crosses_high_confidence(0.5, 0.6) is False


def test_is_reversal_true_on_large_downward_shift_against_uptrend():
    # prior 0.3, trending up to 0.8, then a new update drags it down sharply
    assert is_reversal(prior=0.3, current_posterior=0.8, new_posterior=0.2) is True


def test_is_reversal_false_on_small_shift():
    assert is_reversal(prior=0.3, current_posterior=0.8, new_posterior=0.75) is False


def test_is_reversal_false_when_continuing_the_trend():
    assert is_reversal(prior=0.3, current_posterior=0.5, new_posterior=0.8) is False
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_review.py -v
```
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `causal_graph/review.py`**

```python
HIGH_CONFIDENCE_THRESHOLD = 0.9
REVERSAL_ODDS_MULTIPLE = 2.0


def _odds(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return p / (1 - p)


def crosses_high_confidence(old_posterior: float, new_posterior: float) -> bool:
    return old_posterior < HIGH_CONFIDENCE_THRESHOLD <= new_posterior


def is_reversal(prior: float, current_posterior: float, new_posterior: float) -> bool:
    if new_posterior == current_posterior:
        return False
    trend_up = current_posterior >= prior
    if trend_up and new_posterior < current_posterior:
        shift = _odds(current_posterior) / _odds(new_posterior)
        return shift >= REVERSAL_ODDS_MULTIPLE
    if not trend_up and new_posterior > current_posterior:
        shift = _odds(new_posterior) / _odds(current_posterior)
        return shift >= REVERSAL_ODDS_MULTIPLE
    return False
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/test_review.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Write the failing tests for `scripts/update_causal_edge.py`**

```python
# tests/test_update_causal_edge.py
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage


SCRIPTS = ("add_evidence.py", "add_fact.py", "propose_causal_edge.py", "update_causal_edge.py")


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in SCRIPTS:
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )


def _seed_edge(tmp_path, prior="0.3"):
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    f2 = _run("add_fact.py", ["--topic", "t", "--statement", "B", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    edge = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"fact:{f1}", "--to", f"fact:{f2}",
        "--relation-type", "contributes-to", "--prior", prior,
    ], cwd=tmp_path).stdout.strip()
    return edge, ev


def test_update_causal_edge_applies_moderate_update(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, ev = _seed_edge(tmp_path)
    result = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "2.0",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    edges = storage.load_json_list("t", "causal_edges")
    assert edges[0]["posterior"] > edges[0]["prior"]
    assert len(edges[0]["updates"]) == 1
    assert storage.load_json_list("t", "pending_review") == []


def test_update_causal_edge_diverts_when_crossing_high_confidence_without_falsification(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, ev = _seed_edge(tmp_path, prior="0.5")
    result = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "50.0",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "queued for review" in result.stdout
    edges = storage.load_json_list("t", "causal_edges")
    assert edges[0]["updates"] == []  # not applied
    pending = storage.load_json_list("t", "pending_review")
    assert len(pending) == 1
    assert pending[0]["kind"] == "causal_edge_update"
```

- [ ] **Step 6: Run to verify failure**

```bash
pytest tests/test_update_causal_edge.py -v
```
Expected: FAIL (`scripts/update_causal_edge.py` does not exist yet).

- [ ] **Step 7: Implement `scripts/update_causal_edge.py`**

```python
#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from causal_graph import bayes, review, storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id, validate_likelihood_ratio


def _needs_review(edge: dict, new_posterior: float):
    if review.crosses_high_confidence(edge["posterior"], new_posterior) and not edge["falsification_checks"]:
        return True, "high-confidence threshold crossed without a recorded falsification check"
    if review.is_reversal(edge["prior"], edge["posterior"], new_posterior):
        return True, "evidence reverses the edge's trend beyond the configured margin"
    return False, None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--edge-id", required=True, dest="edge_id")
    p.add_argument("--evidence-id", required=True, dest="evidence_id")
    p.add_argument("--likelihood-ratio", required=True, type=float, dest="likelihood_ratio")
    p.add_argument("--correlated-with", default="", dest="correlated_with")
    args = p.parse_args()

    correlated_with = [c.strip() for c in args.correlated_with.split(",") if c.strip()]
    lr = validate_likelihood_ratio(args.likelihood_ratio)

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        edges = storage.load_json_list(args.topic, "causal_edges")
        edge = next((e for e in edges if e["id"] == args.edge_id), None)
        if edge is None:
            raise ValidationError(f"unknown edge id: {args.edge_id}")
        known_evidence = {e["id"] for e in storage.load_json_list(args.topic, "evidence")}
        if args.evidence_id not in known_evidence:
            raise ValidationError(f"unknown evidence id: {args.evidence_id}")

        new_update = {
            "evidence_id": args.evidence_id,
            "likelihood_ratio": lr,
            "correlated_with": correlated_with,
            "agent": current_agent_id(),
            "timestamp": time.time(),
        }
        trial_updates = edge["updates"] + [new_update]
        new_posterior = bayes.compute_posterior(edge["prior"], trial_updates)

        needs_review, reason = _needs_review(edge, new_posterior)
        if needs_review:
            item = {
                "id": new_id("rev"),
                "kind": "causal_edge_update",
                "edge_id": edge["id"],
                "proposed_update": new_update,
                "proposed_posterior": new_posterior,
                "reason": reason,
                "tier": "normal",
                "created_at": time.time(),
            }
            storage.commit_mutation(
                args.topic, current_agent_id(), "update_causal_edge.py", vars(args),
                [("pending_review", item)],
            )
            print(f"queued for review: {item['id']} ({reason})")
            return

        edge["updates"] = trial_updates
        edge["posterior"] = new_posterior
        edge["last_updated"] = time.time()
        storage.commit_mutation(
            args.topic, current_agent_id(), "update_causal_edge.py", vars(args),
            [("causal_edges", edge)],
        )
        print(edge["id"])


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 8: Run to verify pass**

```bash
pytest tests/test_update_causal_edge.py -v
```
Expected: 2 passed.

- [ ] **Step 9: Commit**

```bash
git add causal_graph/review.py scripts/update_causal_edge.py tests/test_review.py tests/test_update_causal_edge.py
git commit -m "Add review triggers and update_causal_edge.py with falsification gate"
```

---

### Task 12: `record_falsification_check.py`

**Files:**
- Create: `scripts/record_falsification_check.py`
- Test: `tests/test_falsification_gate.py`

**Interfaces:**
- Consumes: same storage/lock/cli pattern as prior scripts.
- Produces: CLI `record_falsification_check.py --topic T --edge-id ID --alternative-hypothesis TEXT --counterevidence-search TEXT --result TEXT`. Appends to the edge's `falsification_checks[]`. Also proves end-to-end that recording a check unblocks a high-confidence `update_causal_edge.py` call that would otherwise be diverted (Task 11's gate).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_falsification_gate.py
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage

SCRIPTS = ("add_evidence.py", "add_fact.py", "propose_causal_edge.py",
           "update_causal_edge.py", "record_falsification_check.py")


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in SCRIPTS:
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )


def _seed_edge(tmp_path, prior="0.5"):
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    f2 = _run("add_fact.py", ["--topic", "t", "--statement", "B", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    edge = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"fact:{f1}", "--to", f"fact:{f2}",
        "--relation-type", "contributes-to", "--prior", prior,
    ], cwd=tmp_path).stdout.strip()
    return edge, ev


def test_record_falsification_check_appends_entry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, _ = _seed_edge(tmp_path)
    result = _run("record_falsification_check.py", [
        "--topic", "t", "--edge-id", edge,
        "--alternative-hypothesis", "unrelated deploy caused it",
        "--counterevidence-search", "checked deploy logs for the same window",
        "--result", "no correlating deploy found",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    edges = storage.load_json_list("t", "causal_edges")
    assert len(edges[0]["falsification_checks"]) == 1
    assert "no correlating deploy found" in edges[0]["falsification_checks"][0]["counterevidence_search_result"]


def test_falsification_check_unblocks_high_confidence_update(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, ev = _seed_edge(tmp_path, prior="0.5")

    # Without a falsification check, a strong update is diverted (Task 11 behavior).
    diverted = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "50.0",
    ], cwd=tmp_path)
    assert "queued for review" in diverted.stdout

    _run("record_falsification_check.py", [
        "--topic", "t", "--edge-id", edge,
        "--alternative-hypothesis", "alt", "--counterevidence-search", "search", "--result", "null result",
    ], cwd=tmp_path)

    applied = _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "50.0",
    ], cwd=tmp_path)
    assert applied.returncode == 0, applied.stderr
    assert "queued for review" not in applied.stdout
    edges = storage.load_json_list("t", "causal_edges")
    assert len(edges[0]["updates"]) == 1
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_falsification_gate.py -v
```
Expected: FAIL (`scripts/record_falsification_check.py` does not exist yet).

- [ ] **Step 3: Implement `scripts/record_falsification_check.py`**

```python
#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from causal_graph import storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--edge-id", required=True, dest="edge_id")
    p.add_argument("--alternative-hypothesis", required=True, dest="alternative_hypothesis")
    p.add_argument("--counterevidence-search", required=True, dest="counterevidence_search")
    p.add_argument("--result", required=True)
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        edges = storage.load_json_list(args.topic, "causal_edges")
        edge = next((e for e in edges if e["id"] == args.edge_id), None)
        if edge is None:
            raise ValidationError(f"unknown edge id: {args.edge_id}")
        edge["falsification_checks"].append({
            "alternative_hypothesis": args.alternative_hypothesis,
            "counterevidence_search_result": f"{args.counterevidence_search} -> {args.result}",
            "checked_by": current_agent_id(),
            "checked_at": time.time(),
        })
        storage.commit_mutation(
            args.topic, current_agent_id(), "record_falsification_check.py", vars(args),
            [("causal_edges", edge)],
        )
    print(edge["id"])


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/test_falsification_gate.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/record_falsification_check.py tests/test_falsification_gate.py
git commit -m "Add record_falsification_check.py; falsification checks unblock the confidence gate"
```

---

### Task 13: Lifecycle propagation — `revise_fact.py` & `dispute_edge.py`

**Files:**
- Create: `causal_graph/lifecycle.py`
- Create: `scripts/revise_fact.py`
- Create: `scripts/dispute_edge.py`
- Test: `tests/test_lifecycle.py`
- Test: `tests/test_revise_fact_dispute_edge.py`

**Interfaces:**
- Consumes: `causal_graph.graph.downstream_dependents`; `causal_graph.storage`.
- Produces: `causal_graph.lifecycle.propagate_stale(topic: str, node_ref: str) -> list[tuple[str, dict]]` (returns storage-ready writes marking every active downstream dependent `stale`; returns `[]` for `edge:` refs, since causal edges have no downstream dependents in this graph model). CLI `revise_fact.py --topic T --fact-id ID --new-status {contested|superseded|retracted} --reason TEXT [--replacement-statement TEXT]` — if the fact is `verified` and the caller isn't `human`, diverts to `pending_review` (`kind: "fact_revision"`, the "override of a human-verified fact" trigger) instead of applying. CLI `dispute_edge.py --topic T --edge-id ID --new-status {...} --reason TEXT`.

- [ ] **Step 1: Write the failing tests for `causal_graph/lifecycle.py`**

```python
# tests/test_lifecycle.py
from causal_graph import storage
from causal_graph.lifecycle import propagate_stale


def test_propagate_stale_marks_downstream_deduction_and_edge(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage.save_json_list("t", "facts", [{"id": "f1", "status": "active"}, {"id": "f2", "status": "active"}])
    storage.save_json_list("t", "deductions", [
        {"id": "d1", "supporting_fact_ids": ["f1"], "supporting_deduction_ids": [], "status": "active"},
    ])
    storage.save_json_list("t", "causal_edges", [
        {"id": "e1", "from_node": "deduction:d1", "to_node": "fact:f2", "status": "active"},
    ])

    writes = propagate_stale("t", "fact:f1")

    by_id = {r["id"]: r for _, r in writes}
    assert by_id["d1"]["status"] == "stale"
    assert by_id["e1"]["status"] == "stale"


def test_propagate_stale_edge_ref_has_no_dependents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert propagate_stale("t", "edge:e1") == []
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_lifecycle.py -v
```
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `causal_graph/lifecycle.py`**

```python
from . import storage
from .graph import downstream_dependents

_KEY_BY_KIND = {"deduction": "deductions", "edge": "causal_edges"}


def propagate_stale(topic: str, node_ref: str) -> list:
    kind = node_ref.split(":", 1)[0]
    if kind == "edge":
        return []  # causal edges have no downstream dependents in this graph model

    dependents = downstream_dependents(topic, node_ref)
    writes = []
    for ref in dependents:
        dep_kind, rid = ref.split(":", 1)
        key = _KEY_BY_KIND.get(dep_kind)
        if key is None:
            continue
        records = storage.load_json_list(topic, key)
        rec = next((r for r in records if r["id"] == rid), None)
        if rec is not None and rec.get("status") == "active":
            rec["status"] = "stale"
            writes.append((key, rec))
    return writes
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/test_lifecycle.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Write the failing tests for `scripts/revise_fact.py` and `scripts/dispute_edge.py`**

```python
# tests/test_revise_fact_dispute_edge.py
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage

SCRIPTS = ("add_evidence.py", "add_fact.py", "add_deduction.py",
           "propose_causal_edge.py", "revise_fact.py", "dispute_edge.py")


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in SCRIPTS:
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )


def test_retracting_root_fact_cascades_stale_to_dependents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "reported"], cwd=tmp_path).stdout.strip()
    f2 = _run("add_fact.py", ["--topic", "t", "--statement", "B", "--evidence-id", ev, "--confidence", "reported"], cwd=tmp_path).stdout.strip()
    d1 = _run("add_deduction.py", ["--topic", "t", "--claim", "C", "--supports", f"fact:{f1}"], cwd=tmp_path).stdout.strip()
    e1 = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"deduction:{d1}", "--to", f"fact:{f2}",
        "--relation-type", "contributes-to", "--prior", "0.3",
    ], cwd=tmp_path).stdout.strip()

    result = _run("revise_fact.py", [
        "--topic", "t", "--fact-id", f1, "--new-status", "retracted", "--reason", "was wrong",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    facts = {f["id"]: f for f in storage.load_json_list("t", "facts")}
    deds = {d["id"]: d for d in storage.load_json_list("t", "deductions")}
    edges = {e["id"]: e for e in storage.load_json_list("t", "causal_edges")}
    assert facts[f1]["status"] == "retracted"
    assert deds[d1]["status"] != "active"
    assert edges[e1]["status"] != "active"


def test_agent_revising_verified_fact_is_queued_not_applied(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CAUSAL_GRAPH_AGENT_ID", "agent-1")
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()

    result = _run("revise_fact.py", [
        "--topic", "t", "--fact-id", f1, "--new-status", "contested", "--reason", "agent thinks it's wrong",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "queued for review" in result.stdout
    facts = {f["id"]: f for f in storage.load_json_list("t", "facts")}
    assert facts[f1]["status"] == "active"
    pending = storage.load_json_list("t", "pending_review")
    assert pending[0]["kind"] == "fact_revision"


def test_dispute_edge_updates_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    f2 = _run("add_fact.py", ["--topic", "t", "--statement", "B", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    e1 = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"fact:{f1}", "--to", f"fact:{f2}",
        "--relation-type", "contributes-to", "--prior", "0.3",
    ], cwd=tmp_path).stdout.strip()

    result = _run("dispute_edge.py", [
        "--topic", "t", "--edge-id", e1, "--new-status", "contested", "--reason", "questionable",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    edges = {e["id"]: e for e in storage.load_json_list("t", "causal_edges")}
    assert edges[e1]["status"] == "contested"
```

- [ ] **Step 6: Run to verify failure**

```bash
pytest tests/test_revise_fact_dispute_edge.py -v
```
Expected: FAIL (scripts don't exist yet).

- [ ] **Step 7: Implement `scripts/revise_fact.py`**

```python
#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from causal_graph import lifecycle, storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError, new_id


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--fact-id", required=True, dest="fact_id")
    p.add_argument("--new-status", required=True, dest="new_status",
                    choices=["contested", "superseded", "retracted"])
    p.add_argument("--reason", required=True)
    p.add_argument("--replacement-statement", default=None, dest="replacement_statement")
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        facts = storage.load_json_list(args.topic, "facts")
        fact = next((f for f in facts if f["id"] == args.fact_id), None)
        if fact is None:
            raise ValidationError(f"unknown fact id: {args.fact_id}")

        agent_id = current_agent_id()
        if fact["confidence"] == "verified" and agent_id != "human":
            item = {
                "id": new_id("rev"),
                "kind": "fact_revision",
                "fact_id": fact["id"],
                "new_status": args.new_status,
                "reason": args.reason,
                "tier": "normal",
                "created_at": time.time(),
            }
            storage.commit_mutation(
                args.topic, agent_id, "revise_fact.py", vars(args),
                [("pending_review", item)],
            )
            print(f"queued for review: {item['id']} (agent attempted to revise a human-verified fact)")
            return

        fact["status"] = args.new_status
        writes = [("facts", fact)]
        writes += lifecycle.propagate_stale(args.topic, f"fact:{fact['id']}")

        if args.replacement_statement:
            new_fact = dict(fact)
            new_fact["id"] = new_id("fact")
            new_fact["statement"] = args.replacement_statement
            new_fact["status"] = "active"
            new_fact["supersedes_id"] = fact["id"]
            new_fact["created_at"] = time.time()
            new_fact["created_by"] = agent_id
            writes.append(("facts", new_fact))

        storage.commit_mutation(
            args.topic, agent_id, "revise_fact.py", vars(args), writes,
        )
        print(fact["id"])


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 8: Implement `scripts/dispute_edge.py`**

```python
#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from causal_graph import lifecycle, storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--edge-id", required=True, dest="edge_id")
    p.add_argument("--new-status", required=True, dest="new_status",
                    choices=["contested", "superseded", "retracted"])
    p.add_argument("--reason", required=True)
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        edges = storage.load_json_list(args.topic, "causal_edges")
        edge = next((e for e in edges if e["id"] == args.edge_id), None)
        if edge is None:
            raise ValidationError(f"unknown edge id: {args.edge_id}")

        edge["status"] = args.new_status
        writes = [("causal_edges", edge)]
        writes += lifecycle.propagate_stale(args.topic, f"edge:{edge['id']}")

        storage.commit_mutation(
            args.topic, current_agent_id(), "dispute_edge.py", vars(args), writes,
        )
        print(edge["id"])


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 9: Run to verify pass**

```bash
pytest tests/test_revise_fact_dispute_edge.py -v
```
Expected: 3 passed.

- [ ] **Step 10: Commit**

```bash
git add causal_graph/lifecycle.py scripts/revise_fact.py scripts/dispute_edge.py tests/test_lifecycle.py tests/test_revise_fact_dispute_edge.py
git commit -m "Add lifecycle propagation with revise_fact.py and dispute_edge.py"
```

---

### Task 14: `review_queue.py` & `resolve_pending.py`

**Files:**
- Create: `scripts/review_queue.py`
- Create: `scripts/resolve_pending.py`
- Test: `tests/test_review_queue_resolve_pending.py`

**Interfaces:**
- Consumes: `causal_graph.graph.urgency_tier`; `causal_graph.bayes.compute_posterior`; `causal_graph.storage`.
- Produces: CLI `review_queue.py --topic T` — prints a JSON array of pending items, each annotated with a computed `tier` (`urgent`/`normal`) based on the impact of the node the item concerns (edge's `to_node` for `causal_edge_update`, `fact:<id>` for `fact_revision`/`contradiction`). CLI `resolve_pending.py --topic T --id ID --action {approve|reject|amend} [--amended-likelihood-ratio FLOAT]` — `approve` applies the queued change as-is, `amend` applies it with a replaced likelihood ratio (causal edge items only), `reject` discards it; the pending item is always removed from the queue as part of the same commit.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_review_queue_resolve_pending.py
import json
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage

SCRIPTS = ("add_evidence.py", "add_fact.py", "propose_causal_edge.py",
           "update_causal_edge.py", "review_queue.py", "resolve_pending.py")


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in SCRIPTS:
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )


def _seed_pending_edge_update(tmp_path):
    ev = _run("add_evidence.py", ["--topic", "t", "--adapter", "human", "--content", "c", "--source-ref", "r"], cwd=tmp_path).stdout.strip()
    f1 = _run("add_fact.py", ["--topic", "t", "--statement", "A", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    f2 = _run("add_fact.py", ["--topic", "t", "--statement", "B", "--evidence-id", ev, "--confidence", "verified"], cwd=tmp_path).stdout.strip()
    edge = _run("propose_causal_edge.py", [
        "--topic", "t", "--from", f"fact:{f1}", "--to", f"fact:{f2}",
        "--relation-type", "contributes-to", "--prior", "0.5",
    ], cwd=tmp_path).stdout.strip()
    _run("update_causal_edge.py", [
        "--topic", "t", "--edge-id", edge, "--evidence-id", ev, "--likelihood-ratio", "50.0",
    ], cwd=tmp_path)
    return edge, ev


def test_review_queue_lists_pending_with_tier(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    _seed_pending_edge_update(tmp_path)
    result = _run("review_queue.py", ["--topic", "t"], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    items = json.loads(result.stdout)
    assert len(items) == 1
    assert items[0]["tier"] in ("urgent", "normal")


def test_resolve_pending_approve_applies_update(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, _ = _seed_pending_edge_update(tmp_path)
    pending = storage.load_json_list("t", "pending_review")
    item_id = pending[0]["id"]

    result = _run("resolve_pending.py", [
        "--topic", "t", "--id", item_id, "--action", "approve",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert storage.load_json_list("t", "pending_review") == []
    edges = {e["id"]: e for e in storage.load_json_list("t", "causal_edges")}
    assert len(edges[edge]["updates"]) == 1


def test_resolve_pending_reject_discards_without_applying(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, _ = _seed_pending_edge_update(tmp_path)
    item_id = storage.load_json_list("t", "pending_review")[0]["id"]

    _run("resolve_pending.py", ["--topic", "t", "--id", item_id, "--action", "reject"], cwd=tmp_path)
    assert storage.load_json_list("t", "pending_review") == []
    edges = {e["id"]: e for e in storage.load_json_list("t", "causal_edges")}
    assert edges[edge]["updates"] == []


def test_resolve_pending_amend_uses_replacement_ratio(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)
    edge, _ = _seed_pending_edge_update(tmp_path)
    item_id = storage.load_json_list("t", "pending_review")[0]["id"]

    result = _run("resolve_pending.py", [
        "--topic", "t", "--id", item_id, "--action", "amend",
        "--amended-likelihood-ratio", "3.0",
    ], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    edges = {e["id"]: e for e in storage.load_json_list("t", "causal_edges")}
    assert edges[edge]["updates"][0]["likelihood_ratio"] == 3.0
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_review_queue_resolve_pending.py -v
```
Expected: FAIL (scripts don't exist yet).

- [ ] **Step 3: Implement `scripts/review_queue.py`**

```python
#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from causal_graph import graph as graphmod
from causal_graph import storage
from causal_graph.lock import topic_lock


def _base_ref_for(item: dict, topic: str):
    if item["kind"] == "causal_edge_update":
        edges = storage.load_json_list(topic, "causal_edges")
        edge = next((e for e in edges if e["id"] == item["edge_id"]), None)
        return edge["to_node"] if edge else None
    if item["kind"] in ("fact_revision", "contradiction"):
        return f"fact:{item['fact_id']}"
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        items = storage.load_json_list(args.topic, "pending_review")
        for item in items:
            ref = _base_ref_for(item, args.topic)
            item["tier"] = graphmod.urgency_tier(args.topic, ref) if ref else "normal"
    print(json.dumps(items, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Implement `scripts/resolve_pending.py`**

```python
#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from causal_graph import bayes, storage
from causal_graph.cli import current_agent_id
from causal_graph.lock import topic_lock
from causal_graph.schema import ValidationError


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--id", required=True, dest="item_id")
    p.add_argument("--action", required=True, choices=["approve", "reject", "amend"])
    p.add_argument("--amended-likelihood-ratio", type=float, default=None, dest="amended_likelihood_ratio")
    args = p.parse_args()

    with topic_lock(args.topic):
        storage.prepare(args.topic)
        items = storage.load_json_list(args.topic, "pending_review")
        item = next((i for i in items if i["id"] == args.item_id), None)
        if item is None:
            raise ValidationError(f"unknown pending review id: {args.item_id}")

        writes = [("pending_review", {"id": args.item_id, "_delete": True})]

        if args.action != "reject":
            if item["kind"] == "causal_edge_update":
                edges = storage.load_json_list(args.topic, "causal_edges")
                edge = next(e for e in edges if e["id"] == item["edge_id"])
                update = dict(item["proposed_update"])
                if args.action == "amend":
                    if args.amended_likelihood_ratio is None:
                        raise ValidationError("--amended-likelihood-ratio required for amend")
                    update["likelihood_ratio"] = args.amended_likelihood_ratio
                edge["updates"] = edge["updates"] + [update]
                edge["posterior"] = bayes.compute_posterior(edge["prior"], edge["updates"])
                edge["last_updated"] = time.time()
                writes.append(("causal_edges", edge))
            elif item["kind"] == "fact_revision":
                facts = storage.load_json_list(args.topic, "facts")
                fact = next(f for f in facts if f["id"] == item["fact_id"])
                fact["status"] = item["new_status"]
                writes.append(("facts", fact))

        storage.commit_mutation(
            args.topic, current_agent_id(), "resolve_pending.py", vars(args), writes,
        )
    print(f"resolved {args.item_id}: {args.action}")


if __name__ == "__main__":
    try:
        main()
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 5: Run to verify pass**

```bash
pytest tests/test_review_queue_resolve_pending.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/review_queue.py scripts/resolve_pending.py tests/test_review_queue_resolve_pending.py
git commit -m "Add review_queue.py and resolve_pending.py"
```

---

### Task 15: `CodebaseAdapter` and stub adapters

**Files:**
- Create: `adapters/base.py`
- Create: `adapters/codebase_adapter.py`
- Create: `adapters/stubs.py`
- Test: `tests/test_codebase_adapter.py`
- Test: `tests/test_adapter_stubs.py`

**Interfaces:**
- Produces: `adapters.base.EvidenceRecord` (dataclass: `content: str`, `source_ref: str`); `adapters.codebase_adapter.CodebaseAdapter(root: str = ".")` with `.fetch(query: str) -> list[EvidenceRecord]` — case-insensitive substring search over local files, skipping `.git`/`node_modules`/`__pycache__`/`.venv`, returning one record per matching line with `source_ref` as `"<path>:<lineno>"`; `adapters.stubs.{InternalDBAdapter, ManualDocAdapter, ExperimentResultsAdapter}`, each with `.fetch()` raising `NotImplementedError`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_codebase_adapter.py
from adapters.codebase_adapter import CodebaseAdapter


def test_codebase_adapter_finds_matching_line(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("first line\nmemory limit reduced to 2Gi\nlast line\n")
    adapter = CodebaseAdapter(root=str(tmp_path))
    results = adapter.fetch("memory limit")
    assert len(results) == 1
    assert "memory limit reduced" in results[0].content
    assert results[0].source_ref.endswith(":2")


def test_codebase_adapter_skips_git_dir(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "index").write_text("memory limit reduced")
    adapter = CodebaseAdapter(root=str(tmp_path))
    assert adapter.fetch("memory limit") == []


def test_codebase_adapter_no_match_returns_empty(tmp_path):
    (tmp_path / "notes.txt").write_text("nothing relevant here")
    adapter = CodebaseAdapter(root=str(tmp_path))
    assert adapter.fetch("memory limit") == []
```

```python
# tests/test_adapter_stubs.py
import pytest
from adapters.stubs import InternalDBAdapter, ManualDocAdapter, ExperimentResultsAdapter


@pytest.mark.parametrize("cls", [InternalDBAdapter, ManualDocAdapter, ExperimentResultsAdapter])
def test_stub_adapters_raise_not_implemented(cls):
    adapter = cls()
    with pytest.raises(NotImplementedError):
        adapter.fetch("anything")
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_codebase_adapter.py tests/test_adapter_stubs.py -v
```
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `adapters/base.py`**

```python
from dataclasses import dataclass


@dataclass
class EvidenceRecord:
    content: str
    source_ref: str
```

- [ ] **Step 4: Implement `adapters/codebase_adapter.py`**

```python
import os
import re

from .base import EvidenceRecord

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}


class CodebaseAdapter:
    name = "codebase"

    def __init__(self, root: str = "."):
        self.root = root

    def fetch(self, query: str) -> list:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        results = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, "r", errors="ignore") as f:
                        for lineno, line in enumerate(f, start=1):
                            if pattern.search(line):
                                results.append(EvidenceRecord(
                                    content=line.strip(),
                                    source_ref=f"{fpath}:{lineno}",
                                ))
                except (UnicodeDecodeError, PermissionError, IsADirectoryError):
                    continue
        return results
```

- [ ] **Step 5: Implement `adapters/stubs.py`**

```python
from .base import EvidenceRecord  # noqa: F401  (re-exported for consumers)


class _StubAdapter:
    name = "stub"

    def fetch(self, query: str) -> list:
        raise NotImplementedError(
            f"{self.name} is not wired to a real backend yet. "
            "Implement fetch() to connect it to your system, or register "
            "evidence manually via add_evidence.py."
        )


class InternalDBAdapter(_StubAdapter):
    name = "internal_db"


class ManualDocAdapter(_StubAdapter):
    name = "manual_doc"


class ExperimentResultsAdapter(_StubAdapter):
    name = "experiment_results"
```

- [ ] **Step 6: Run to verify pass**

```bash
pytest tests/test_codebase_adapter.py tests/test_adapter_stubs.py -v
```
Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
git add adapters/base.py adapters/codebase_adapter.py adapters/stubs.py tests/test_codebase_adapter.py tests/test_adapter_stubs.py
git commit -m "Add CodebaseAdapter and interface-only stub adapters"
```

---

### Task 16: Golden-scenario integration test & process skill

**Files:**
- Test: `tests/test_golden_scenario.py`
- Create: `.claude/skills/causal-graph-research/SKILL.md`

**Interfaces:**
- Consumes: every script from Tasks 7–14 (end-to-end, via subprocess, exactly as an agent would call them).
- Produces: one integration test proving the full pipeline (spec's Testing section, "golden-scenario test"), and the process skill that documents the 8-step flow from the spec for any driving agent to follow.

- [ ] **Step 1: Write the golden-scenario test**

```python
# tests/test_golden_scenario.py
import subprocess
import sys
import shutil
import pathlib

from causal_graph import storage

ALL_SCRIPTS = (
    "add_evidence.py", "add_fact.py", "add_deduction.py", "propose_causal_edge.py",
    "update_causal_edge.py", "record_falsification_check.py",
    "revise_fact.py", "dispute_edge.py", "review_queue.py", "resolve_pending.py",
)


def _copy_scripts(tmp_path):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    for name in ALL_SCRIPTS:
        shutil.copy(repo_root / "scripts" / name, tmp_path / "scripts" / name)


def _run(script, args, cwd):
    result = subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=cwd, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"{script} {args} failed: {result.stderr}"
    return result.stdout.strip()


def test_golden_scenario_two_facts_one_deduction_one_edge_two_updates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _copy_scripts(tmp_path)

    ev1 = _run("add_evidence.py", [
        "--topic", "etl", "--adapter", "internal_db",
        "--content", "ETL pod OOM-killed at 02:14 UTC", "--source-ref", "k8s-events/etl-worker-7",
    ], tmp_path)
    ev2 = _run("add_evidence.py", [
        "--topic", "etl", "--adapter", "codebase",
        "--content", "memory limit cut 4Gi to 2Gi in PR #482", "--source-ref", "deployment.yaml:12",
    ], tmp_path)

    f1 = _run("add_fact.py", [
        "--topic", "etl", "--statement", "ETL job OOM-killed at 02:14 UTC",
        "--evidence-id", ev1, "--confidence", "verified",
    ], tmp_path)
    f2 = _run("add_fact.py", [
        "--topic", "etl", "--statement", "Memory limit reduced 4Gi to 2Gi",
        "--evidence-id", ev2, "--confidence", "verified",
    ], tmp_path)

    d1 = _run("add_deduction.py", [
        "--topic", "etl", "--claim", "Memory headroom shrank",
        "--supports", f"fact:{f2}", "--logic-note", "limit halved",
    ], tmp_path)

    e1 = _run("propose_causal_edge.py", [
        "--topic", "etl", "--from", f"deduction:{d1}", "--to", f"fact:{f1}",
        "--relation-type", "contributes-to", "--prior", "0.3",
    ], tmp_path)

    _run("update_causal_edge.py", [
        "--topic", "etl", "--edge-id", e1, "--evidence-id", ev1, "--likelihood-ratio", "3.0",
    ], tmp_path)
    _run("update_causal_edge.py", [
        "--topic", "etl", "--edge-id", e1, "--evidence-id", ev2, "--likelihood-ratio", "2.0",
    ], tmp_path)

    facts = storage.load_json_list("etl", "facts")
    deductions = storage.load_json_list("etl", "deductions")
    edges = storage.load_json_list("etl", "causal_edges")
    audit = storage.read_audit("etl")

    assert len(facts) == 2
    assert len(deductions) == 1
    assert len(edges) == 1
    assert len(edges[0]["updates"]) == 2
    assert 0.3 < edges[0]["posterior"] < 1.0
    assert len(audit) == 7  # 2 evidence + 2 facts + 1 deduction + 1 edge + ... 
```

> Note while implementing: count the audit entries actually produced (2 `add_evidence.py` + 2 `add_fact.py` + 1 `add_deduction.py` + 1 `propose_causal_edge.py` + 2 `update_causal_edge.py` = 8) and correct the literal `7` above to `8` before this step is considered done — this is exactly the kind of arithmetic a golden-scenario test exists to pin down precisely, not approximate.

- [ ] **Step 2: Run to verify it passes**

```bash
pytest tests/test_golden_scenario.py -v
```
Expected: 1 passed (after correcting the audit-entry count per the note above).

- [ ] **Step 3: Write the process skill**

```markdown
---
name: causal-graph-research
description: Use when investigating a research topic where an agent's tendency to form a verdict early and only seek confirming evidence would be costly — structures the investigation as an auditable fact/deduction graph plus a Bayesian-updated causal graph, mutated only through deterministic scripts in scripts/.
---

# Causal Graph Research

Follow these steps. Steps 2 and 5–7 are conditional — skip what a simple
question doesn't need; see "Keeping it simple" below.

1. **Define the research question.** Pick a short topic slug (e.g.
   `etl-oom-failure`); every script call below takes `--topic <slug>`.

2. **Elicit human input (optional, skippable).** Ask the user for (a) any
   known facts/evidence they already have, and (b) any suspected
   cause/hypothesis.
   - (a) Register directly via `add_evidence.py` / `add_fact.py`, same as
     any other source.
   - (b) Register as a deduction or causal-edge proposal with an explicit
     neutral/low prior (e.g. 0.3, not 0.8) — a hypothesis to test, not a
     starting verdict.
   - Skip this step entirely if the user wants you to discover and decide
     everything autonomously.

3. **Gather evidence.** For each source:
   - Local repo: use your own grep/read tools (or `adapters.codebase_adapter.CodebaseAdapter`),
     then register each finding with `python scripts/add_evidence.py --topic T --adapter codebase --content "..." --source-ref "path:line"`.
   - Web: use your own web-search tool, then register with `--adapter external_web --source-ref <url>`.
   - Human-asserted: `--adapter human --source-ref "conversation:<date>"`.
   - `InternalDBAdapter` / `ManualDocAdapter` / `ExperimentResultsAdapter` are stubs — only use them once wired to a real backend; otherwise register that evidence manually too.

4. **Extract facts.** For each evidence item, if it supports a grounded
   claim: `python scripts/add_fact.py --topic T --statement "..." --evidence-id <id> --confidence {verified|reported|inferred}`.
   If a new fact structurally contradicts an existing one, add
   `--contradicts <fact_id>` — this queues it for review rather than
   silently coexisting.

5. **Propose deductions** (skip if there's no multi-fact claim to make):
   `python scripts/add_deduction.py --topic T --claim "..." --supports "fact:ID,fact:ID2"`.

6. **Propose causal edges** (skip if there's no causal claim to make):
   `python scripts/propose_causal_edge.py --topic T --from fact:ID|deduction:ID --to fact:ID|deduction:ID --relation-type "contributes-to" --prior 0.3`.
   Priors start neutral-to-low; they earn confidence through evidence, not assertion.

7. **Update edges as evidence arrives:**
   `python scripts/update_causal_edge.py --topic T --edge-id ID --evidence-id ID --likelihood-ratio N [--correlated-with "id1,id2"]`.
   - Use `--correlated-with` when new evidence isn't independent of prior
     evidence already applied to this edge (e.g. two reports from the same
     underlying source) — this prevents double-counting.
   - If the command prints `queued for review: ...`, the update was **not**
     applied. Common reasons: it would cross the high-confidence threshold
     without a recorded falsification check, or it reverses the edge's
     trend sharply. For the falsification case, run
     `python scripts/record_falsification_check.py --topic T --edge-id ID --alternative-hypothesis "..." --counterevidence-search "..." --result "..."`
     (a genuine null result is a valid answer) and retry the update.

8. **Check and act on the review queue periodically:**
   `python scripts/review_queue.py --topic T` lists pending items with a
   computed `tier`.
   - `urgent` items (high graph impact): surface to the human immediately
     in this session — don't wait for a periodic summary.
   - `normal` items: mention the count in your next summary; resolve with
     `python scripts/resolve_pending.py --topic T --id ID --action {approve|reject|amend} [--amended-likelihood-ratio N]`.

## Keeping it simple

The full pipeline is for topics complex enough to need it. A simple
question should be answerable with 1–2 calls to `add_fact.py` and nothing
else — don't force evidence adapters, deductions, or causal edges onto a
topic that doesn't need them.
```

- [ ] **Step 4: Commit**

```bash
mkdir -p .claude/skills/causal-graph-research
git add tests/test_golden_scenario.py .claude/skills/causal-graph-research/SKILL.md
git commit -m "Add golden-scenario integration test and causal-graph-research process skill"
```

---

## Plan Self-Review Notes

- **Spec coverage:** Architecture (Tasks 1, 3–4 for layers 2–3, 15 for layer 1, 16 for layer 4) — covered. Data model (Task 2 schema, Tasks 7–14 write the actual fields) — covered. Deterministic scripts list — all ten scripts have a task. Evidence adapters — covered (Task 15), including the agent-mediated `human`/`external_web` convention (Task 16 skill). Process skill — Task 16. Falsification checkpoint — Task 11 (gate) + Task 12 (recording). Evidence independence — Task 5 (`compute_posterior`/`group_correlated`). Lifecycle & correction propagation — Task 13. Scope & simplicity — reflected in Task 16's skill doc and the conditional framing throughout. Error handling / multi-file consistency — Task 4. Testing section's five named test types (unit, golden-scenario, adapter contract, falsification-gate, evidence-independence, retraction-propagation, consistency-repair) all map to a specific task's test file.
- **Placeholder scan:** no TBD/TODO; the one explicit "correct this number" note in Task 16 Step 1 is intentional — the exact audit-entry count depends on execution order the implementer must verify by running the test, not a deferred design decision.
- **Type consistency:** `commit_mutation(topic, agent_id, script, args, writes: list[tuple[str, dict]])` used identically from Task 4 onward; `node_ref` string format (`"fact:<id>"`/`"deduction:<id>"`/`"edge:<id>"`) consistent across `graph.py`, `lifecycle.py`, `review_queue.py`; `Confidence`/`Status` enum values match their spec definitions throughout.
