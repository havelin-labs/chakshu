import uuid

from chakshu.services.threads import Thread, classify


def _marker(finding_id: str) -> str:
    return f"**High: x**\n\nbody\n\n<!-- chakshu:f={finding_id} -->"


def test_classify_threads():
    ids = {name: str(uuid.uuid4()) for name in ("gone", "still", "fresh", "fixed-by-dev", "waved-off")}
    threads = [
        Thread("t-gone", resolved=False, outdated=True, first_comment=_marker(ids["gone"])),
        Thread("t-still", resolved=False, outdated=True, first_comment=_marker(ids["still"])),
        Thread("t-fresh", resolved=False, outdated=False, first_comment=_marker(ids["fresh"])),
        Thread("t-fixed", resolved=True, outdated=True, first_comment=_marker(ids["fixed-by-dev"])),
        Thread("t-waved", resolved=True, outdated=False, first_comment=_marker(ids["waved-off"])),
        Thread("t-human", resolved=False, outdated=True, first_comment="Can we rename this?"),
    ]

    scan = classify(threads, still_found={ids["still"]})

    assert scan.resolve == ["t-gone"]
    assert scan.fixed == {ids["gone"], ids["fixed-by-dev"]}
    assert scan.dismissed == {ids["waved-off"]}
