"""URL safety checks for the NEXORA browser agent.

The agent runs a real browser, so user-supplied URLs must never be able to reach
loopback, link-local, private, reserved, or cloud-metadata addresses. Validation
happens before the request reaches Playwright and again at the Pydantic boundary.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import HTTPException, status

BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata",
    "metadata.google.internal",
    "instance-data",
}
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal")
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}


def _ip_is_public(address: str) -> bool:
    """Return True only for globally routable IP literals."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False

    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped

    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_public_host(hostname: str) -> bool:
    """Resolve a hostname and require every answer to be a public IP."""
    try:
        answers = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False

    addresses = {answer[4][0] for answer in answers}
    if not addresses:
        return False
    return all(_ip_is_public(address) for address in addresses)


def validate_public_url(value: object) -> str:
    """Validate and return a URL that is safe for the browser to navigate to.

    Raises ``ValueError`` for use as a Pydantic validator. ``is_safe`` wraps this
    for callers that prefer a boolean check.
    """
    raw = str(value).strip()
    parsed = urlparse(raw)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError("Only http and https URLs are allowed.")
    if not parsed.hostname:
        raise ValueError("A hostname is required.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in the URL are not allowed.")
    if parsed.port is not None and parsed.port not in ALLOWED_PORTS:
        raise ValueError("Only ports 80 and 443 are allowed.")

    host = parsed.hostname.rstrip(".").lower()
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_SUFFIXES):
        raise ValueError("This hostname is not allowed.")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if not _ip_is_public(host):
            raise ValueError("Private, loopback, or reserved IP addresses are not allowed.")
    elif not _resolve_public_host(host):
        raise ValueError("Hostname could not be resolved to a public IP address.")

    return raw


def is_safe_url(value: object) -> bool:
    """Boolean wrapper around :func:`validate_public_url`."""
    try:
        validate_public_url(value)
    except ValueError:
        return False
    return True


def unsafe_url_error(value: object) -> HTTPException:
    """Build the HTTP error used by routes that validate outside Pydantic."""
    try:
        validate_public_url(value)
    except ValueError as exc:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsafe URL.")
