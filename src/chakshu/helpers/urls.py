import ipaddress
from urllib.parse import urlparse

LOCAL_HOSTNAMES = {"localhost", "host.docker.internal"}


def is_public_url(url: str) -> bool:
    """True if GitHub could plausibly reach this URL from the internet."""
    host = (urlparse(url).hostname or "").lower()
    if not host or host in LOCAL_HOSTNAMES or host.endswith((".local", ".localhost", ".internal")):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "." in host
    return address.is_global
