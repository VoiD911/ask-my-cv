from ask_my_cv.text import normalize_text


def test_collapses_runs_of_whitespace() -> None:
    assert normalize_text("a  b\r\nc") == "a b c"


def test_single_space_is_unchanged() -> None:
    assert normalize_text("a b c") == "a b c"


def test_single_newline_is_unchanged() -> None:
    assert normalize_text("a\nb") == "a\nb"


def test_text_without_whitespace_runs_is_unchanged() -> None:
    assert normalize_text("hello world") == "hello world"
