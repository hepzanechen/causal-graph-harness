from __future__ import annotations

import math
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
    if not math.isfinite(value):
        raise ValidationError(f"likelihood_ratio must be finite, got {value}")
    if value <= 0:
        raise ValidationError(f"likelihood_ratio must be > 0, got {value}")
    return float(value)
