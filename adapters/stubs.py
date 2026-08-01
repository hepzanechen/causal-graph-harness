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
