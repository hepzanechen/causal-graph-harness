import json
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path

from benchmarks.pioneer import benchmark


ROOT = Path(__file__).resolve().parents[1]


class PioneerBenchmarkTests(unittest.TestCase):
    def test_has_expected_six_case_difficulty_mix(self):
        cases = benchmark.list_cases()
        self.assertEqual([case["id"] for case in cases], [
            "p01", "p02", "p03", "p04", "p05", "p06",
        ])
        self.assertEqual(Counter(case["difficulty"] for case in cases), {
            "straightforward": 2,
            "multi_hop": 2,
            "misleading": 1,
            "compound": 1,
        })

    def test_public_cases_and_sealed_gold_are_internally_consistent(self):
        for metadata in benchmark.list_cases():
            case_id = metadata["id"]
            case = benchmark._read_json(benchmark._path_for(benchmark.CASES_DIR, case_id))
            gold = benchmark._read_json(benchmark._path_for(benchmark.GOLD_DIR, case_id))

            self.assertEqual(case["id"], case_id)
            self.assertGreaterEqual(len(case["evidence"]), 6)
            evidence_ids = [item["id"] for item in case["evidence"]]
            self.assertEqual(len(evidence_ids), len(set(evidence_ids)))
            self.assertTrue(all(item.startswith(f"ev-{case_id}-") for item in evidence_ids))
            self.assertTrue(set(gold["critical_evidence_ids"]).issubset(evidence_ids))
            self.assertGreaterEqual(len(gold["required_chain"]), 3)
            self.assertTrue(gold["root_causes"])

            public_heading = benchmark._normalize(case["title"] + " " + case["prompt"])
            for root in gold["root_causes"]:
                self.assertNotIn(benchmark._normalize(root["fault"]), public_heading)

        compound = benchmark._read_json(benchmark.GOLD_DIR / "p06.json")
        self.assertEqual(len(compound["root_causes"]), 2)

    def test_load_case_does_not_return_evidence_or_gold(self):
        public = benchmark.load_case("p05")
        self.assertNotIn("evidence", public)
        self.assertNotIn("root_causes", public)
        self.assertIn("answer_contract", public)

    def test_search_requires_selection_and_reads_by_opaque_id(self):
        with self.assertRaises(benchmark.BenchmarkError):
            benchmark.search_evidence("p03", "")

        results = benchmark.search_evidence("p03", "promotion retry")
        self.assertGreaterEqual(len(results), 2)
        self.assertIn("ev-p03-03", {item["id"] for item in results})
        complete = benchmark.read_evidence("p03", "ev-p03-03")
        self.assertIn("retry", complete["content"].casefold())

    def test_invalid_identifiers_cannot_escape_case_directory(self):
        for value in ("../gold/p01", "/tmp/p01", "P01", "p01.json"):
            with self.assertRaises(benchmark.BenchmarkError):
                benchmark.load_case(value)

    def test_perfect_answer_scores_joint_success(self):
        for metadata in benchmark.list_cases():
            case_id = metadata["id"]
            gold = benchmark._read_json(benchmark.GOLD_DIR / f"{case_id}.json")
            answer = {
                "hypotheses": [{
                    "rank": 1,
                    "root_causes": gold["root_causes"],
                    "causal_chain": gold["required_chain"],
                    "confidence": 0.9,
                    "evidence_ids": gold["critical_evidence_ids"],
                }]
            }
            score = benchmark.score_answer(case_id, answer)
            self.assertTrue(score["joint_success"], case_id)
            self.assertEqual(score["causal_chain_recall"], 1.0)
            self.assertEqual(score["critical_evidence_recall"], 1.0)

    def test_incomplete_compound_answer_fails_root_match(self):
        gold = benchmark._read_json(benchmark.GOLD_DIR / "p06.json")
        answer = {
            "hypotheses": [{
                "rank": 1,
                "root_causes": gold["root_causes"][:1],
                "causal_chain": gold["required_chain"][:2],
                "confidence": 0.8,
                "evidence_ids": gold["critical_evidence_ids"][:3],
            }]
        }
        score = benchmark.score_answer("p06", answer)
        self.assertFalse(score["root_cause_exact_match"])
        self.assertFalse(score["joint_success"])
        self.assertLess(score["causal_chain_recall"], 1.0)

    def test_cli_lists_cases_as_json(self):
        result = subprocess.run(
            [sys.executable, "-m", "benchmarks.pioneer.benchmark", "list"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)), 6)

    def test_protocol_covers_each_case_and_keeps_gold_sealed(self):
        protocol = benchmark._read_json(benchmark.ROOT / "protocol.json")
        case_ids = [case["id"] for case in benchmark.list_cases()]
        self.assertEqual(protocol["case_ids"], case_ids)
        self.assertEqual(protocol["runs_per_case_per_condition"], 1)
        self.assertFalse(protocol["limits"]["live_web"])
        self.assertFalse(protocol["isolation"]["agent_can_access_gold"])
        self.assertFalse(protocol["conditions"]["baseline"]["causal_graph_skill"])
        self.assertTrue(protocol["conditions"]["treatment"]["causal_graph_skill"])


if __name__ == "__main__":
    unittest.main()
