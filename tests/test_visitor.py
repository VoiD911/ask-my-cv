from ask_my_cv.visitor import client_ip, visitor_id


def test_cloudfront_header_is_used_only_when_trusted() -> None:
    headers = {"cloudfront-viewer-address": "203.0.113.7:51234"}
    assert client_ip(headers, "10.0.0.1", "cloudfront") == "203.0.113.7"
    assert client_ip(headers, "10.0.0.1", "none") == "10.0.0.1"


def test_ipv6_viewer_address_keeps_the_address() -> None:
    headers = {"cloudfront-viewer-address": "2001:db8::1:443"}
    assert client_ip(headers, None, "cloudfront") == "2001:db8::1"


def test_missing_header_falls_back_to_peer_then_unknown() -> None:
    assert client_ip({}, "10.0.0.1", "cloudfront") == "10.0.0.1"
    assert client_ip({}, None, "none") == "unknown"


def test_visitor_id_is_a_keyed_hash() -> None:
    a = visitor_id("203.0.113.7", "k" * 32)
    assert a == visitor_id("203.0.113.7", "k" * 32)
    assert len(a) == 16 and a != visitor_id("203.0.113.7", "z" * 32)
    assert "203" not in a
