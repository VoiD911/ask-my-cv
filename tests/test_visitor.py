from ask_my_cv.visitor import client_ip, visitor_id


def test_cloudfront_header_is_used_only_when_trusted() -> None:
    headers = {"cloudfront-viewer-address": "203.0.113.7:51234"}
    assert client_ip(headers, "10.0.0.1", "cloudfront") == "203.0.113.7"
    assert client_ip(headers, "10.0.0.1", "none") == "10.0.0.1"


def test_ipv6_is_bucketed_by_64() -> None:
    a = client_ip({"cloudfront-viewer-address": "2001:db8::1:443"}, None, "cloudfront")
    b = client_ip({"cloudfront-viewer-address": "2001:db8::ffff:443"}, None, "cloudfront")
    assert a == b == "2001:db8::/64"


def test_viewer_address_without_port_or_garbage() -> None:
    def h(value: str) -> dict[str, str]:
        return {"cloudfront-viewer-address": value}

    assert client_ip(h("203.0.113.7"), None, "cloudfront") == "203.0.113.7"
    assert client_ip(h("::1"), None, "cloudfront") == "::/64"
    assert client_ip(h("garbage"), "10.0.0.1", "cloudfront") == "10.0.0.1"


def test_ipv6_peer_is_bucketed_too() -> None:
    assert client_ip({}, "2001:db8::5", "none") == "2001:db8::/64"


def test_missing_header_falls_back_to_peer_then_unknown() -> None:
    assert client_ip({}, "10.0.0.1", "cloudfront") == "10.0.0.1"
    assert client_ip({}, None, "none") == "unknown"


def test_visitor_id_is_a_keyed_hash() -> None:
    a = visitor_id("203.0.113.7", "k" * 32)
    assert a == visitor_id("203.0.113.7", "k" * 32)
    assert len(a) == 16 and a != visitor_id("203.0.113.7", "z" * 32)
    assert "203" not in a
