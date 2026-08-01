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
