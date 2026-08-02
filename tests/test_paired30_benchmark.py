import json
import unittest
from pathlib import Path
import tempfile

from benchmarks.paired30 import benchmark
from benchmarks.paired30 import run_opencode


class Paired30BenchmarkTests(unittest.TestCase):
    def test_has_thirty_distinct_cases(self):
        cases = benchmark.list_cases()
        self.assertEqual(len(cases), 30)
        self.assertEqual(len({case["title"] for case in cases}), 30)

    def test_cases_and_gold_are_consistent(self):
        cases = benchmark._cases()
        gold = benchmark._read_json(benchmark.GOLD_PATH)
        self.assertEqual(set(cases), set(gold))
        for case_id, case in cases.items():
            ids = {item["id"] for item in case["evidence"]}
            self.assertEqual(len(ids), 10)
            labels = gold[case_id]
            referenced = set(labels["root_event_ids"])
            referenced.update(labels["accepted_causal_event_ids"])
            referenced.update(labels["critical_supporting_evidence_ids"])
            referenced.update(labels["accepted_supporting_evidence_ids"])
            referenced.update(labels["falsifying_evidence_ids"])
            referenced.update(labels["distractor_evidence_ids"])
            for path in labels["required_paths"]:
                referenced.update(path)
            self.assertTrue(referenced <= ids, case_id)
            self.assertFalse(set(labels["root_event_ids"]) & set(labels["distractor_evidence_ids"]))

    def test_perfect_answer_scores_perfectly(self):
        gold = benchmark._read_json(benchmark.GOLD_PATH)
        for case_id, labels in gold.items():
            answer = {
                "root_event_ids": labels["root_event_ids"],
                "causal_paths": labels["required_paths"],
                "supporting_evidence_ids": labels["critical_supporting_evidence_ids"],
                "counterevidence_ids": labels["falsifying_evidence_ids"],
                "rejected_distractor_ids": labels["distractor_evidence_ids"],
                "confidence": 1.0,
                "explanation": "gold fixture",
            }
            score = benchmark.score_answer(case_id, answer)
            self.assertEqual(score["root_f1"], 1.0, case_id)
            self.assertEqual(score["chain_f1"], 1.0, case_id)
            self.assertTrue(score["joint_success"], case_id)
            self.assertEqual(score["brier_joint_success"], 0.0, case_id)

    def test_paraphrase_is_irrelevant_because_ids_are_scored(self):
        labels = benchmark._read_json(benchmark.GOLD_PATH)["c01"]
        answer = {
            "root_event_ids": labels["root_event_ids"],
            "causal_paths": labels["required_paths"],
            "supporting_evidence_ids": labels["critical_supporting_evidence_ids"],
            "counterevidence_ids": labels["falsifying_evidence_ids"],
            "rejected_distractor_ids": labels["distractor_evidence_ids"],
            "confidence": 0.8,
            "explanation": "Any semantically faithful wording can go here.",
        }
        self.assertTrue(benchmark.score_answer("c01", answer)["joint_success"])

    def test_trace_records_searches_and_reads(self):
        old_path = benchmark.TRACE_PATH
        try:
            import tempfile
            from pathlib import Path
            with tempfile.TemporaryDirectory() as directory:
                benchmark.TRACE_PATH = Path(directory) / "trace.jsonl"
                found = benchmark.search_evidence("c01", "cache memory")
                benchmark.read_evidence("c01", found[0]["id"])
                records = [json.loads(line) for line in benchmark.TRACE_PATH.read_text().splitlines()]
                self.assertEqual([record["action"] for record in records], ["search", "read"])
        finally:
            benchmark.TRACE_PATH = old_path

    def test_runner_extracts_answer_and_usage_from_event_stream(self):
        answer = {
            "root_event_ids": ["ev-c01-05"],
            "causal_paths": [["ev-c01-05", "ev-c01-01"]],
            "supporting_evidence_ids": ["ev-c01-05"],
            "counterevidence_ids": ["ev-c01-04"],
            "rejected_distractor_ids": ["ev-c01-02"],
            "confidence": 0.8,
            "explanation": "fixture",
        }
        events = [
            {"type": "text", "part": {"text": json.dumps(answer)}},
            {"type": "step_finish", "sessionID": "session-1", "part": {
                "tokens": {"input": 100, "output": 20, "reasoning": 3}, "cost": 0.01,
            }},
        ]
        self.assertEqual(run_opencode._extract_answer(events), answer)
        self.assertEqual(run_opencode._usage(events)["input_tokens"], 100)
        self.assertEqual(run_opencode._usage(events)["model_cost"], 0.01)

    def test_runner_sandboxes_one_case_and_never_copies_gold(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "bare"
            run_opencode._prepare_sandbox(run_opencode.Job("c01", "bare", 1), run_dir)
            cases = json.loads((run_dir / "cases.json").read_text())
            self.assertEqual([case["id"] for case in cases], ["c01"])
            self.assertFalse((run_dir / "gold.json").exists())
            self.assertFalse((run_dir / "AGENTS.md").exists())

            graph_dir = Path(directory) / "graph"
            run_opencode._prepare_sandbox(
                run_opencode.Job("c01", "graph", 1), graph_dir, Path("/home/kt/zero")
            )
            self.assertTrue((graph_dir / "AGENTS.md").is_file())
            self.assertTrue((graph_dir / "scripts" / "add_fact.py").is_file())
            self.assertFalse((graph_dir / "gold.json").exists())


if __name__ == "__main__":
    unittest.main()
