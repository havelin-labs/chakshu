"""Turn the agent's findings into what gets posted. Pure functions.

Each finding gets a deterministic ID from (PR, reviewer, path, category,
title). The ID rides along in a hidden HTML comment, so a later run can see it
was already posted and skip it.
"""

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from chakshu.core import ids
from chakshu.helpers import severity

MARKER_RE = re.compile(r"<!-- chakshu:f=([0-9a-f-]{36}) -->")
SEVERITY_LABEL = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low", "info": "Note"}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    severity: str
    category: str
    title: str
    body: str
    suggestion: str | None = None
    skill: str | None = None

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> "Finding":
        return cls(
            path=normalize_path(str(raw.get("path", ""))),
            line=int(raw.get("line") or 1),
            severity=str(raw.get("severity", "info")),
            category=str(raw.get("category", "maintainability")),
            title=str(raw.get("title", "")).strip(),
            body=str(raw.get("body", "")).strip(),
            suggestion=raw.get("suggestion") or None,
            skill=raw.get("skill") or None,
        )


@dataclass(frozen=True)
class Identified:
    finding: Finding
    id: uuid.UUID

    @property
    def marker(self) -> str:
        return f"<!-- chakshu:f={self.id} -->"


@dataclass
class Plan:
    inline: list[Identified] = field(default_factory=list)
    summary_only: list[Identified] = field(default_factory=list)
    repeats: int = 0

    @property
    def new(self) -> list[Identified]:
        return self.inline + self.summary_only


def normalize_path(path: str) -> str:
    path = path.strip().replace("\\", "/").removeprefix("./")
    return path.removeprefix("code/")


def _title_key(title: str) -> str:
    return " ".join(title.lower().split())


def identify(ns: uuid.UUID, pr_key: uuid.UUID, reviewer_id: uuid.UUID, f: Finding) -> Identified:
    return Identified(f, ids.eid(ns, "finding", pr_key, reviewer_id, f.path, f.category, _title_key(f.title)))


def choose(findings: Iterable[Finding], min_severity: str, max_findings: int) -> list[Finding]:
    """At or above the threshold, most severe first, capped."""
    kept = [f for f in findings if f.title and severity.rank(f.severity) >= severity.rank(min_severity)]
    kept.sort(key=lambda f: -severity.rank(f.severity))
    return kept[:max_findings]


def plan(items: Sequence[Identified], commentable: dict[str, set[int]], already: set[str]) -> Plan:
    result = Plan()
    for item in items:
        if str(item.id) in already:
            result.repeats += 1
        elif item.finding.line in commentable.get(item.finding.path, set()):
            result.inline.append(item)
        else:
            result.summary_only.append(item)
    return result


def existing_markers(bodies: Iterable[str | None]) -> set[str]:
    return {match for body in bodies for match in MARKER_RE.findall(body or "")}


def _heading(f: Finding) -> str:
    return f"**{SEVERITY_LABEL.get(f.severity, f.severity.title())}: {f.title}**"


def render_comment(item: Identified, reviewer: str) -> str:
    f = item.finding
    parts = [_heading(f), f.body]
    if f.suggestion:
        parts.append(f"```suggestion\n{f.suggestion.rstrip()}\n```")
    source = f"{reviewer} · {f.skill}" if f.skill else reviewer
    parts.append(f"<sub>{source} · {f.category}</sub>\n{item.marker}")
    return "\n\n".join(parts)


def render_review_body(reviewer: str, summary: str, review_plan: Plan) -> str:
    lines = [f"### Chakshu · {reviewer}", "", summary.strip() or "No summary."]
    if review_plan.summary_only:
        lines += ["", "**Outside the changed lines**", ""]
        for item in review_plan.summary_only:
            f = item.finding
            lines.append(f"- `{f.path}:{f.line}`: {_heading(f)}. {f.body} {item.marker}")
    if not review_plan.new:
        lines += ["", "Nothing new to report."]
    if review_plan.repeats:
        lines += [
            "",
            f"<sub>{review_plan.repeats} finding(s) already raised on this PR were not repeated.</sub>",
        ]
    return "\n".join(lines)


def conclusion(findings: Iterable[Finding], fail_on: str | None) -> str:
    return "failure" if any(severity.at_least(f.severity, fail_on) for f in findings) else "success"


def counts(findings: Iterable[Finding]) -> str:
    tally: dict[str, int] = {}
    for f in findings:
        tally[f.severity] = tally.get(f.severity, 0) + 1
    if not tally:
        return "No findings"
    ordered = sorted(tally.items(), key=lambda kv: -severity.rank(kv[0]))
    return ", ".join(f"{n} {SEVERITY_LABEL.get(s, s).lower()}" for s, n in ordered)
