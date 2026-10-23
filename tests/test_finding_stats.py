import uuid

from sqlalchemy import select

from chakshu.db.models import OutcomeSource, PostedFinding, Run
from chakshu.helpers.findings import Finding, Identified
from chakshu.services import finding_stats


def _item(skill: str) -> Identified:
    finding = Finding("a.py", 1, "high", "bug", f"t-{uuid.uuid4()}", "b", skill=skill)
    return Identified(finding, uuid.uuid4())


async def test_outcomes_roll_up_per_skill(db, seed_runs):
    [run_id] = await seed_runs(1)
    run = await db.get(Run, run_id)
    money = [_item("money") for _ in range(3)]
    tests = [_item("tests")]
    await finding_stats.record_posted(db, run, money + tests)
    await finding_stats.record_posted(db, run, money[:1])  # reposting is a no-op
    await finding_stats.record_outcomes(
        db, fixed={str(money[0].id), str(money[1].id)}, dismissed={str(money[2].id)}
    )
    await finding_stats.record_outcomes(db, fixed=set(), dismissed={str(money[0].id)})  # verdicts stick
    await db.commit()

    stats = {s["skill"]: s for s in await finding_stats.per_skill(db, days=30)}

    assert stats["money"] == {
        "account": "acme",
        "reviewer": "default",
        "skill": "money",
        "posted": 3,
        "fixed": 2,
        "dismissed": 1,
        "open": 0,
        "fix_rate": 0.67,
    }
    assert stats["tests"]["open"] == 1 and stats["tests"]["fix_rate"] is None


async def test_outcomes_remember_how_they_were_decided(db, seed_runs):
    [run_id] = await seed_runs(1)
    run = await db.get(Run, run_id)
    changed, resolved, replied = _item("a"), _item("a"), _item("a")
    await finding_stats.record_posted(db, run, [changed, resolved, replied])
    await finding_stats.record_outcomes(db, fixed={str(changed.id)}, dismissed={str(resolved.id)})
    await finding_stats.record_outcomes(
        db, fixed=set(), dismissed={str(replied.id)}, source=OutcomeSource.REPLY
    )
    await db.commit()

    sources = {
        row.id: row.outcome_source
        for row in (await db.scalars(select(PostedFinding).where(PostedFinding.run_id == run_id))).all()
    }
    assert sources == {
        changed.id: OutcomeSource.CODE_CHANGE,
        resolved.id: OutcomeSource.THREAD_RESOLVED,
        replied.id: OutcomeSource.REPLY,
    }
