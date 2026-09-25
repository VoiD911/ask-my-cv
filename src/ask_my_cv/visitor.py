from __future__ import annotations

import hashlib
import hmac
import ipaddress
from collections.abc import Mapping
from typing import Literal

TrustedProxy = Literal["none", "cloudfront"]


def _normalize(raw: str) -> str | None:
    """Adresse normalisée ; IPv6 regroupée par /64 (un client contrôle au moins un /64)."""
    for candidate in (raw.rsplit(":", 1)[0], raw):
        try:
            addr = ipaddress.ip_address(candidate.strip().strip("[]"))
        except ValueError:
            continue
        if addr.version == 6:
            return f"{ipaddress.ip_network(f'{addr}/64', strict=False).network_address}/64"
        return str(addr)
    return None


def client_ip(headers: Mapping[str, str], peer: str | None, trusted_proxy: TrustedProxy) -> str:
    """IP du visiteur. L'en-tête CloudFront n'est cru que si l'API n'est joignable que par
    CloudFront."""
    if trusted_proxy == "cloudfront":
        viewer = headers.get("cloudfront-viewer-address")
        if viewer and (ip := _normalize(viewer)):
            return ip
    if peer:
        return _normalize(peer) or peer
    return "unknown"


def visitor_id(ip: str, secret: str) -> str:
    """Pseudonyme stable du visiteur : HMAC-SHA256, jamais l'IP elle-même."""
    return hmac.new(secret.encode("utf-8"), ip.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
