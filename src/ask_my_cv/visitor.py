from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from typing import Literal

TrustedProxy = Literal["none", "cloudfront"]


def client_ip(headers: Mapping[str, str], peer: str | None, trusted_proxy: TrustedProxy) -> str:
    """IP du visiteur. L'en-tête CloudFront n'est cru que si l'API n'est joignable que par
    CloudFront."""
    if trusted_proxy == "cloudfront":
        viewer = headers.get("cloudfront-viewer-address")
        if viewer:
            return viewer.rsplit(":", 1)[0]
    return peer or "unknown"


def visitor_id(ip: str, secret: str) -> str:
    """Pseudonyme stable du visiteur : HMAC-SHA256, jamais l'IP elle-même."""
    return hmac.new(secret.encode("utf-8"), ip.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
