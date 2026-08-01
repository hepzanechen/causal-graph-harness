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
