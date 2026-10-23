"""Reviewers as the portal edits them, and the files in the reviewers repo they become. No I/O.

A draft is one reviewer folder in editable form: the reviewer.yaml fields, the
text of RULES.md and each local skill's SKILL.md split into frontmatter and body.
Shared skills are only referenced by name.
"""

import re
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from chakshu.helpers.catalog import (
    NAME_PATTERN,
    REVIEWERS_DIR,
    SHARED_PREFIX,
    SHARED_SKILLS_DIR,
    ReviewerSpec,
    validation_errors,
)

RULES_FILE = "RULES.md"
SKILL_FILE = "SKILL.md"
# Claude skills allow up to 1024 characters of description.
MAX_SKILL_DESCRIPTION = 1024
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)(.*)\Z", re.S)


class SkillDraft(BaseModel):
    name: str
    description: str = ""
    body: str = ""
    # Other SKILL.md frontmatter (allowed-tools and so on), kept as it was.
    extra: dict[str, Any] = Field(default_factory=dict)


class ReviewerDraft(BaseModel):
    """Loose on purpose: ReviewerSpec does the validation, so errors read the same as in a sync."""

    account: str
    name: str
    product: str | None = None
    description: str | None = None
    owner_team: str = ""
    model: str | None = None
    repos: list[str] = Field(default_factory=lambda: ["*"])
    paths: list[str] = Field(default_factory=list)
    auto: list[str] = Field(default_factory=list)
    connectors: list[str] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)
    fail_check_on: str | None = None
    tools: list[str] = Field(default_factory=list)
    rules: str = ""  # RULES.md text; empty means no rules file
    skills: list[SkillDraft] = Field(default_factory=list)
    shared_skills: list[str] = Field(default_factory=list)  # names under shared/skills/


def _blank_to_none(value: str | None) -> str | None:
    return (value.strip() or None) if value else None


def _clean(items: list[str]) -> list[str]:
    return [item.strip() for item in items if item.strip()]


def to_spec(draft: ReviewerDraft) -> tuple[ReviewerSpec | None, list[str]]:
    """The reviewer.yaml this draft makes, or the reasons it can't be saved."""
    errors: list[str] = []
    seen: set[str] = set()
    for skill in draft.skills:
        if not re.match(NAME_PATTERN, skill.name):
            errors.append(f"skill '{skill.name}': use lowercase letters, digits and dashes")
        if skill.name in seen:
            errors.append(f"skill '{skill.name}' is listed twice")
        seen.add(skill.name)
        if not skill.description.strip():
            errors.append(f"skill '{skill.name}': add a description, Claude uses it to pick the skill")
        elif len(skill.description) > MAX_SKILL_DESCRIPTION:
            errors.append(
                f"skill '{skill.name}': keep the description under {MAX_SKILL_DESCRIPTION} characters"
            )
    shared = _clean(draft.shared_skills)
    try:
        spec = ReviewerSpec.model_validate(
            {
                "name": draft.name.strip(),
                "product": _blank_to_none(draft.product),
                "description": _blank_to_none(draft.description),
                "owner_team": draft.owner_team.strip(),
                "model": _blank_to_none(draft.model),
                "repos": _clean(draft.repos) or ["*"],
                "paths": _clean(draft.paths),
                "auto": draft.auto,
                "skills": [s.name for s in draft.skills] + [f"{SHARED_PREFIX}{n}" for n in shared],
                "limits": draft.limits,
                "fail_check_on": _blank_to_none(draft.fail_check_on),
                "tools": draft.tools,
                "connectors": _clean(draft.connectors),
            }
        )
    except ValidationError as exc:
        return None, validation_errors(exc) + errors
    return (None, errors) if errors else (spec, [])


def render_yaml(spec: ReviewerSpec) -> str:
    """reviewer.yaml with only the fields that differ from the defaults, in the documented order."""
    data = spec.model_dump(mode="json", exclude_defaults=True)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100)


def render_skill(skill: SkillDraft) -> str:
    meta = {"name": skill.name, "description": skill.description.strip(), **skill.extra}
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000)
    return f"---\n{front}---\n\n{skill.body.strip()}\n"


def parse_skill(text: str, name: str) -> SkillDraft:
    """A SKILL.md back into a draft. The folder name wins over the frontmatter's name."""
    meta: dict[str, Any] = {}
    body = text
    match = FRONTMATTER.match(text)
    if match:
        try:
            loaded = yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            loaded = None
        if isinstance(loaded, dict):
            meta, body = loaded, match.group(2)
    extra = {k: v for k, v in meta.items() if k not in ("name", "description")}
    return SkillDraft(
        name=name, description=str(meta.get("description") or ""), body=body.strip("\n"), extra=extra
    )


def from_files(account: str, raw: dict[str, Any], rules: str, skill_texts: dict[str, str]) -> ReviewerDraft:
    """A draft from a parsed reviewer.yaml, its rules text and its local skills' SKILL.md texts."""
    skills = [str(s) for s in raw.get("skills") or []]
    local = [s for s in skills if not s.startswith(SHARED_PREFIX)]
    known = set(ReviewerDraft.model_fields) - {"account", "rules", "skills", "shared_skills"}
    return ReviewerDraft(
        account=account,
        **{k: v for k, v in raw.items() if k in known and v is not None},
        rules=rules,
        skills=[parse_skill(skill_texts.get(s, ""), s) for s in local],
        shared_skills=[s.removeprefix(SHARED_PREFIX) for s in skills if s.startswith(SHARED_PREFIX)],
    )


def folder_path(folder: str) -> str:
    return f"{REVIEWERS_DIR}/{folder}"


def shared_skill_path(name: str) -> str:
    return f"{SHARED_SKILLS_DIR}/{name}/{SKILL_FILE}"


def rules_file(raw: dict[str, Any]) -> str:
    return str(raw.get("rules") or RULES_FILE)


def render_files(
    spec: ReviewerSpec, draft: ReviewerDraft, folder: str, existing: set[str]
) -> dict[str, str | None]:
    """Every file to write (text) or delete (None) under reviewers/<folder>/.

    `existing` is every file path in the repo now. Removing a local skill deletes
    its whole folder; files Chakshu doesn't manage are left alone.
    """
    base = folder_path(folder)
    files: dict[str, str | None] = {f"{base}/reviewer.yaml": render_yaml(spec)}
    rules_path = f"{base}/{RULES_FILE}"
    if draft.rules.strip():
        files[rules_path] = draft.rules.strip() + "\n"
    elif rules_path in existing:
        files[rules_path] = None
    kept = {s.name for s in draft.skills}
    for skill in draft.skills:
        files[f"{base}/skills/{skill.name}/{SKILL_FILE}"] = render_skill(skill)
    skills_dir = f"{base}/skills/"
    for path in existing:
        if path.startswith(skills_dir) and path.removeprefix(skills_dir).split("/", 1)[0] not in kept:
            files[path] = None
    return files
