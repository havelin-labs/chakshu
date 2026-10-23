from pathlib import Path

import yaml

from chakshu.helpers import reviewer_drafts as drafts
from chakshu.helpers.catalog import load_catalog
from chakshu.helpers.reviewer_drafts import ReviewerDraft, SkillDraft


def _draft(**overrides) -> ReviewerDraft:
    values = {
        "account": "acme",
        "name": "payments",
        "product": "Payments",
        "owner_team": "payments",
        "repos": ["payments-*", " "],
        "paths": ["src/refunds/**"],
        "auto": ["opened"],
        "limits": {"max_findings": 5},
        "fail_check_on": "high",
        "rules": "Amounts are in cents.\n\n",
        "skills": [SkillDraft(name="money", description="Spots rounding bugs.", body="# Money\n\nCheck it.")],
        "shared_skills": ["secure-coding"],
    }
    return ReviewerDraft(**(values | overrides))


def _write_all(root: Path, files: dict[str, str | None]) -> None:
    for rel, text in files.items():
        if text is None:
            continue
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_rendered_files_load_back_as_a_valid_reviewer(tmp_path):
    spec, errors = drafts.to_spec(_draft())
    assert errors == []
    files = drafts.render_files(spec, _draft(), "payments", existing=set())
    _write_all(tmp_path, files | {"shared/skills/secure-coding/SKILL.md": "---\nname: secure-coding\n---\n"})

    [reviewer] = load_catalog(tmp_path)

    assert reviewer.errors == []
    assert reviewer.spec.repos == ["payments-*"]
    assert reviewer.spec.skills == ["money", "shared/secure-coding"]
    assert reviewer.spec.limits.max_findings == 5
    assert files["reviewers/payments/RULES.md"] == "Amounts are in cents.\n"


def test_reviewer_yaml_leaves_out_defaults():
    spec, _ = drafts.to_spec(_draft(product="", limits={}, rules="", skills=[], shared_skills=[]))
    data = yaml.safe_load(drafts.render_yaml(spec))
    assert list(data) == ["name", "owner_team", "repos", "paths", "auto", "fail_check_on"]


def test_skill_frontmatter_round_trips():
    skill = SkillDraft(
        name="money", description="Spots: rounding bugs", body="# Money\n", extra={"allowed-tools": "Read"}
    )
    text = drafts.render_skill(skill)

    assert text.startswith(
        "---\nname: money\ndescription: 'Spots: rounding bugs'\nallowed-tools: Read\n---\n"
    )
    assert drafts.parse_skill(text, "money") == SkillDraft(
        name="money", description="Spots: rounding bugs", body="# Money", extra={"allowed-tools": "Read"}
    )


def test_skill_without_frontmatter_keeps_its_text_as_the_body():
    assert drafts.parse_skill("Just text", "loose") == SkillDraft(name="loose", body="Just text")


def test_from_files_splits_local_and_shared_skills():
    raw = {"name": "payments", "owner_team": "payments", "skills": ["money", "shared/secure-coding"]}
    draft = drafts.from_files("acme", raw, "Rules", {"money": "---\nname: x\ndescription: d\n---\nBody"})

    assert draft.shared_skills == ["secure-coding"]
    assert draft.skills == [SkillDraft(name="money", description="d", body="Body")]
    assert draft.rules == "Rules"


def test_validation_errors_name_the_fields():
    bad = _draft(
        name="Not Valid",
        owner_team="",
        auto=["closed"],
        skills=[SkillDraft(name="Bad_Name", description=""), SkillDraft(name="ok", description="x" * 2000)],
    )
    spec, errors = drafts.to_spec(bad)

    assert spec is None
    assert any(e.startswith("name:") for e in errors)
    assert any(e.startswith("owner_team:") for e in errors)
    assert any(e.startswith("auto.0:") for e in errors)
    assert "skill 'Bad_Name': use lowercase letters, digits and dashes" in errors
    assert "skill 'Bad_Name': add a description, Claude uses it to pick the skill" in errors
    assert "skill 'ok': keep the description under 1024 characters" in errors


def test_removing_a_skill_deletes_its_folder_and_empty_rules_delete_the_file():
    existing = {
        "reviewers/payments/reviewer.yaml",
        "reviewers/payments/RULES.md",
        "reviewers/payments/skills/money/SKILL.md",
        "reviewers/payments/skills/money/notes.md",
        "reviewers/payments/skills/old/SKILL.md",
        "reviewers/payments/skills/old/examples/a.py",
        "reviewers/other/skills/old/SKILL.md",
    }
    draft = _draft(rules="  ")
    spec, _ = drafts.to_spec(draft)

    files = drafts.render_files(spec, draft, "payments", existing)

    assert files["reviewers/payments/RULES.md"] is None
    assert files["reviewers/payments/skills/old/SKILL.md"] is None
    assert files["reviewers/payments/skills/old/examples/a.py"] is None
    assert "reviewers/payments/skills/money/notes.md" not in files
    assert "reviewers/other/skills/old/SKILL.md" not in files


async def test_proposals_catch_name_clashes_and_missing_skills_and_connectors(db, seed_runs):
    from sqlalchemy import select

    from chakshu.db.models import Installation, Repo, Reviewer
    from chakshu.services import reviewer_editor

    await seed_runs(0)
    installation = await db.scalar(select(Installation))
    existing = await db.scalar(select(Reviewer))
    target = reviewer_editor.ReviewersRepo(
        repo=Repo(full_name="acme/chakshu-reviewers", default_branch="main"),
        client=None,
        sha="c" * 40,
        paths={"reviewers/fresh/reviewer.yaml", "shared/skills/secure-coding/SKILL.md"},
    )

    async def check(name: str, reviewer=None, **overrides) -> list[str]:
        draft = _draft(name=name, **overrides)
        folder = reviewer.source_path.removeprefix("reviewers/") if reviewer else name
        return await reviewer_editor._check(db, installation, target, draft, folder, reviewer)

    assert await check("default") == ["name: 'default' is already used by reviewers/default"]
    assert await check("default", existing) == []
    assert await check("fresh") == ["name: reviewers/fresh already exists in acme/chakshu-reviewers"]
    assert await check("new-one", shared_skills=["nope"], connectors=["jira"]) == [
        "shared skill 'nope' isn't in shared/skills",
        "connector 'jira' isn't set up in Chakshu",
    ]
