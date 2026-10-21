import uuid

from chakshu.core import ids


def test_product_namespace_is_fixed():
    # Changing this would change every ID ever issued. It must never move.
    assert str(ids.PRODUCT_NS) == "d529e7b7-dbda-568d-af0a-d9f007824bf1"


def test_same_inputs_give_same_id():
    ns = ids.instance_ns("github.com", 123456)
    assert ids.eid(ns, "org", 987654) == ids.eid(ns, "org", 987654)


def test_instances_never_overlap():
    a = ids.instance_ns("github.com", 123456)
    b = ids.instance_ns("github.com", 777001)
    assert ids.eid(a, "org", 987654) != ids.eid(b, "org", 987654)


def test_host_is_case_insensitive():
    assert ids.instance_ns("GitHub.com", 1) == ids.instance_ns("github.com", 1)


def test_separator_in_parts_cannot_cause_collisions():
    ns = uuid.uuid4()
    assert ids.eid(ns, "x", "a|b") != ids.eid(ns, "x", "a", "b")


def test_kind_separates_entities():
    ns = uuid.uuid4()
    assert ids.eid(ns, "repo", 5) != ids.eid(ns, "org", 5)


def test_key_format_is_versioned():
    assert ids.key("reviewer", 42, "payments") == "v1|reviewer|42|payments"
