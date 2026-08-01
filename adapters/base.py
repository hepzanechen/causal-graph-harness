from dataclasses import dataclass


@dataclass
class EvidenceRecord:
    content: str
    source_ref: str
