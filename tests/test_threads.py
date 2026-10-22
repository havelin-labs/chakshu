import uuid

from chakshu.services.threads import Thread, to_resolve

FIXED, STILL_THERE = str(uuid.uuid4()), str(uuid.uuid4())


def _marker(finding_id: str) -> str:
    return f"**High: x**\n\nbody\n\n<!-- chakshu:f={finding_id} -->"


def test_only_outdated_chakshu_threads_whose_finding_is_gone():
    threads = [
        Thread("fixed", resolved=False, outdated=True, first_comment=_marker(FIXED)),
        Thread("still-there", resolved=False, outdated=True, first_comment=_marker(STILL_THERE)),
        Thread("not-outdated", resolved=False, outdated=False, first_comment=_marker(FIXED)),
        Thread("already-resolved", resolved=True, outdated=True, first_comment=_marker(FIXED)),
        Thread("human", resolved=False, outdated=True, first_comment="Can we rename this?"),
    ]

    assert to_resolve(threads, still_found={STILL_THERE}) == ["fixed"]
