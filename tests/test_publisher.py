import uuid

from chakshu.helpers import findings as f
from chakshu.helpers.diff import commentable_lines

PATCH = """@@ -10,4 +10,5 @@ def refund(amount):
     total = 0
-    value = float(amount)
+    value = Decimal(amount)
+    check(value)
     return value
\\ No newline at end of file
@@ -40,2 +41,2 @@
-old()
+new()
 keep()"""


def test_commentable_lines_cover_added_and_context_lines():
    assert commentable_lines(PATCH) == {10, 11, 12, 13, 41, 42}
    assert commentable_lines(None) == set()


def _finding(**kw):
    base = {
        "path": "./code/src/pay.py",
        "line": 11,
        "severity": "high",
        "category": "bug",
        "title": "Float money",
    }
    return f.Finding.parse(base | {"body": "Use Decimal."} | kw)


def test_parse_normalizes_paths():
    assert _finding().path == "src/pay.py"


def test_choose_filters_sorts_and_caps():
    items = [
        _finding(severity="low", title="a"),
        _finding(severity="critical", title="b"),
        _finding(title="c"),
    ]
    chosen = f.choose(items, "medium", 1)
    assert [x.title for x in chosen] == ["b"]


def test_plan_splits_inline_summary_and_repeats():
    ns, pr, rev = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    inside = f.identify(ns, pr, rev, _finding(line=12, title="inside"))
    outside = f.identify(ns, pr, rev, _finding(line=99, title="outside"))
    repeat = f.identify(ns, pr, rev, _finding(line=10, title="seen"))

    plan = f.plan([inside, outside, repeat], {"src/pay.py": {10, 11, 12}}, {str(repeat.id)})

    assert plan.inline == [inside] and plan.summary_only == [outside] and plan.repeats == 1


def test_same_problem_gets_the_same_id_even_if_the_line_moves():
    ns, pr, rev = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    a = f.identify(ns, pr, rev, _finding(line=11, title="Float  money"))
    b = f.identify(ns, pr, rev, _finding(line=30, title="float money"))
    assert a.id == b.id


def test_markers_round_trip():
    item = f.identify(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), _finding(suggestion="value = Decimal(x)"))
    body = f.render_comment(item, "payments-reviewer")
    assert "```suggestion\nvalue = Decimal(x)\n```" in body
    assert f.existing_markers([body, None]) == {str(item.id)}


def test_conclusion_and_counts():
    items = [_finding(severity="high"), _finding(severity="low", title="x")]
    assert f.conclusion(items, "high") == "failure"
    assert f.conclusion(items, "critical") == "success"
    assert f.conclusion(items, None) == "success"
    assert f.counts(items) == "1 high, 1 low"
