"""Deterministic IDs.

Every row gets a UUIDv5. The same inputs always produce the same ID, so a
webhook GitHub retries, a resync of the reviewers repo or a reinstall of the
app all land on rows that already exist instead of creating duplicates.

The tree of namespaces:

    NAMESPACE_DNS
      -> PRODUCT_NS        uuid5(DNS, "chakshu.havelin.in")
        -> instance ns     uuid5(PRODUCT_NS, "v1|instance|<github host>|app|<app id>")
          -> entity ids    uuid5(instance ns, "v1|<kind>|<part>|<part>...")

Two installs of Chakshu always have different GitHub App IDs, so their
instance namespaces differ and their IDs can never collide, even when they
review the same organization.

Hash GitHub's numeric IDs, never logins or repo names: those can be renamed.
These IDs are predictable by design. Never use one as a secret.
"""

import unicodedata
import uuid

SCHEME_VERSION = "v1"
PRODUCT_DOMAIN = "chakshu.havelin.in"
PRODUCT_NS = uuid.uuid5(uuid.NAMESPACE_DNS, PRODUCT_DOMAIN)


def _escape(part: object) -> str:
    text = unicodedata.normalize("NFC", str(part))
    # Escape the separator so ("a|b",) and ("a", "b") can never hash the same.
    return text.replace("%", "%25").replace("|", "%7C")


def key(kind: str, *parts: object) -> str:
    """Canonical, versioned name that gets hashed: 'v1|kind|part|part'."""
    return "|".join([SCHEME_VERSION, _escape(kind), *(_escape(p) for p in parts)])


def instance_ns(github_host: str, app_id: int) -> uuid.UUID:
    return uuid.uuid5(PRODUCT_NS, key("instance", github_host.lower(), "app", app_id))


def eid(ns: uuid.UUID, kind: str, *parts: object) -> uuid.UUID:
    return uuid.uuid5(ns, key(kind, *parts))
