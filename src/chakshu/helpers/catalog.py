"""Read and validate a reviewers repo checked out on disk.

Layout:
    reviewers/<folder>/reviewer.yaml
    reviewers/<folder>/RULES.md
    reviewers/<folder>/skills/<skill>/SKILL.md
    shared/skills/<skill>/SKILL.md

One broken folder never hides the others: each reviewer carries its own errors.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from chakshu.helpers.severity import Severity

REVIEWERS_DIR = "reviewers"
SHARED_SKILLS_DIR = "shared/skills"
SHARED_PREFIX = "shared/"
NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}$"

AutoEvent = Literal["opened", "ready_for_review", "synchronize", "reopened"]


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_usd: float | None = Field(default=None, gt=0, le=100)
    max_findings: int = Field(default=10, ge=1, le=50)
    min_severity: Severity = "medium"


class ReviewerSpec(BaseModel):
    """reviewer.yaml"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=NAME_PATTERN)
    product: str | None = None
    description: str | None = None
    owner_team: str = Field(min_length=1)
    model: str | None = None
    repos: list[str] = Field(default_factory=lambda: ["*"])
    paths: list[str] = Field(default_factory=list)
    auto: list[AutoEvent] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    rules: str | None = "RULES.md"
    limits: Limits = Field(default_factory=Limits)
    fail_check_on: Severity | None = None
    # Accepted so teams can write them today; v1 runs read-only tools and no connectors.
    tools: list[str] = Field(default_factory=list)
    connectors: list[str] = Field(default_factory=list)


@dataclass
class ParsedReviewer:
    folder: str
    spec: ReviewerSpec | None
    errors: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.spec.name if self.spec else self.folder

    @property
    def source_path(self) -> str:
        return f"{REVIEWERS_DIR}/{self.folder}"


def skill_dir(root: Path, folder: str, skill: str) -> Path:
    """Where a skill named in reviewer.yaml lives."""
    if skill.startswith(SHARED_PREFIX):
        return root / SHARED_SKILLS_DIR / skill.removeprefix(SHARED_PREFIX)
    return root / REVIEWERS_DIR / folder / "skills" / skill


def validation_errors(exc: ValidationError) -> list[str]:
    return [
        f"{'.'.join(str(p) for p in err['loc']) or 'reviewer.yaml'}: {err['msg']}" for err in exc.errors()
    ]


def parse_reviewer(root: Path, folder: Path) -> ParsedReviewer:
    parsed = ParsedReviewer(folder=folder.name, spec=None)
    path = folder / "reviewer.yaml"
    if not path.is_file():
        parsed.errors.append("reviewer.yaml is missing")
        return parsed
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        parsed.spec = ReviewerSpec.model_validate(raw)
    except yaml.YAMLError as exc:
        parsed.errors.append(f"reviewer.yaml isn't valid YAML: {exc}")
        return parsed
    except ValidationError as exc:
        parsed.errors.extend(validation_errors(exc))
        return parsed

    spec = parsed.spec
    for skill in spec.skills:
        if not (skill_dir(root, folder.name, skill) / "SKILL.md").is_file():
            parsed.errors.append(f"skill '{skill}' has no SKILL.md")
    if spec.rules and not (folder / spec.rules).is_file():
        if spec.rules != "RULES.md":  # the default is optional
            parsed.errors.append(f"rules file '{spec.rules}' doesn't exist")
        spec.rules = None
    return parsed


def load_catalog(root: Path) -> list[ParsedReviewer]:
    base = root / REVIEWERS_DIR
    if not base.is_dir():
        return []
    parsed = [parse_reviewer(root, folder) for folder in sorted(base.iterdir()) if folder.is_dir()]

    seen: dict[str, str] = {}
    for reviewer in parsed:
        if reviewer.spec is None:
            continue
        other = seen.setdefault(reviewer.name, reviewer.folder)
        if other != reviewer.folder:
            reviewer.errors.append(f"name '{reviewer.name}' is already used by reviewers/{other}")
    return parsed
