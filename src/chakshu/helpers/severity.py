from typing import Literal

Severity = Literal["info", "low", "medium", "high", "critical"]
SEVERITIES: tuple[Severity, ...] = ("info", "low", "medium", "high", "critical")


def rank(severity: str) -> int:
    """Position in SEVERITIES; unknown values sort lowest."""
    return SEVERITIES.index(severity) if severity in SEVERITIES else -1


def at_least(severity: str, threshold: str | None) -> bool:
    return threshold is not None and rank(severity) >= rank(threshold)
