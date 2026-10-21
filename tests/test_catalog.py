from pathlib import Path

from chakshu.helpers.catalog import load_catalog

TEMPLATE = Path(__file__).parent.parent / "templates" / "chakshu-reviewers"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_valid_reviewer_with_local_and_shared_skills(tmp_path):
    _write(tmp_path, "shared/skills/secure-coding/SKILL.md", "---\nname: secure-coding\n---\n")
    _write(tmp_path, "reviewers/payments/skills/money/SKILL.md", "---\nname: money\n---\n")
    _write(tmp_path, "reviewers/payments/RULES.md", "Use cents.")
    _write(
        tmp_path,
        "reviewers/payments/reviewer.yaml",
        "name: payments-reviewer\nowner_team: payments\nrepos: [payments-*]\n"
        "skills: [money, shared/secure-coding]\nauto: [opened]\nfail_check_on: high\n",
    )

    [reviewer] = load_catalog(tmp_path)

    assert reviewer.errors == []
    assert reviewer.name == "payments-reviewer"
    assert reviewer.source_path == "reviewers/payments"
    assert reviewer.spec.rules == "RULES.md"
    assert reviewer.spec.limits.min_severity == "medium"


def test_broken_folders_report_errors_without_hiding_others(tmp_path):
    _write(tmp_path, "reviewers/good/reviewer.yaml", "name: good\nowner_team: core\n")
    _write(tmp_path, "reviewers/bad-yaml/reviewer.yaml", "name: [unclosed\n")
    _write(tmp_path, "reviewers/no-team/reviewer.yaml", "name: no-team\n")
    _write(tmp_path, "reviewers/missing-skill/reviewer.yaml", "name: ms\nowner_team: core\nskills: [nope]\n")
    (tmp_path / "reviewers" / "empty").mkdir()

    by_folder = {r.folder: r for r in load_catalog(tmp_path)}

    assert by_folder["good"].errors == []
    assert "isn't valid YAML" in by_folder["bad-yaml"].errors[0]
    assert by_folder["no-team"].errors[0].startswith("owner_team")
    assert by_folder["missing-skill"].errors == ["skill 'nope' has no SKILL.md"]
    assert by_folder["empty"].errors == ["reviewer.yaml is missing"]


def test_duplicate_names_are_flagged(tmp_path):
    _write(tmp_path, "reviewers/a/reviewer.yaml", "name: same\nowner_team: x\n")
    _write(tmp_path, "reviewers/b/reviewer.yaml", "name: same\nowner_team: y\n")

    errors = {r.folder: r.errors for r in load_catalog(tmp_path)}

    assert errors["a"] == []
    assert errors["b"] == ["name 'same' is already used by reviewers/a"]


def test_starter_template_is_valid():
    reviewers = load_catalog(TEMPLATE)
    assert reviewers and all(r.errors == [] for r in reviewers)
