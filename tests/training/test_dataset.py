import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ml.dataset import (
    ADVERSARIAL_PATH,
    HANDWRITTEN_PATH,
    RECRUITER_EVAL_PATH,
    AdversarialCase,
    Example,
    build_datasets,
    fingerprint,
    load_adversarial,
    read_jsonl,
    read_parquet,
)
from ml.fetch import Source


def test_real_handwritten_file_is_valid() -> None:
    rows = read_jsonl(HANDWRITTEN_PATH, "handwritten")
    assert {e.label for e in rows} == {0, 1}
    texts = [e.text for e in rows]
    assert len(texts) == len(set(texts))
    assert any("é" in t for t in texts) and any(t.startswith("What") for t in texts)


def test_real_adversarial_file_is_valid_and_disjoint_from_training() -> None:
    cases = load_adversarial(ADVERSARIAL_PATH)
    assert {c.expect for c in cases} == {"block", "allow"}
    train_texts = {e.text for e in read_jsonl(HANDWRITTEN_PATH, "handwritten")}
    assert not ({c.text for c in cases} & train_texts)


def test_read_parquet_with_label_column_and_fixed_label(tmp_path: Path) -> None:
    path = tmp_path / "x.parquet"
    pq.write_table(pa.table({"text": ["a", "b"], "label": [0, 1]}), path)
    labelled = Source(
        name="x", url="u", sha256="0" * 64, license="MIT", role="train", label_column="label"
    )
    fixed = Source(
        name="x", url="u", sha256="0" * 64, license="MIT", role="eval_gandalf", fixed_label=1
    )
    assert [e.label for e in read_parquet(path, labelled)] == [0, 1]
    assert [e.label for e in read_parquet(path, fixed)] == [1, 1]


def test_build_datasets_routes_roles_and_rejects_leakage(tmp_path: Path) -> None:
    for name in ["tr", "te", "gd"]:
        pq.write_table(
            pa.table({"text": [f"{name}-1", f"{name}-2"], "label": [0, 1]}),
            tmp_path / f"{name}.parquet",
        )
    sources = [
        Source(
            name="tr", url="u", sha256="0" * 64, license="MIT", role="train", label_column="label"
        ),
        Source(
            name="te",
            url="u",
            sha256="0" * 64,
            license="MIT",
            role="eval_deepset",
            label_column="label",
        ),
        Source(
            name="gd", url="u", sha256="0" * 64, license="MIT", role="eval_gandalf", fixed_label=1
        ),
    ]
    hand = tmp_path / "hand.jsonl"
    hand.write_text(json.dumps({"text": "question", "label": 0}) + "\n", encoding="utf-8")
    adv = tmp_path / "adv.jsonl"
    adv.write_text(json.dumps({"text": "attaque", "expect": "block"}) + "\n", encoding="utf-8")
    domain = tmp_path / "domain.jsonl"
    domain.write_text(json.dumps({"text": "question domaine", "label": 0}) + "\n", encoding="utf-8")

    ds = build_datasets(sources, tmp_path, hand, adv, domain)
    assert [e.text for e in ds.train] == ["tr-1", "tr-2", "question"]
    assert [e.text for e in ds.eval_deepset] == ["te-1", "te-2"]
    assert [e.label for e in ds.eval_gandalf] == [1, 1]
    assert ds.adversarial == [AdversarialCase(text="attaque", expect="block")]
    assert [e.text for e in ds.eval_domain] == ["question domaine"]

    adv.write_text(json.dumps({"text": "question", "expect": "allow"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        build_datasets(sources, tmp_path, hand, adv, domain)

    adv.write_text(json.dumps({"text": "attaque", "expect": "block"}) + "\n", encoding="utf-8")
    domain.write_text(json.dumps({"text": "question", "label": 0}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        build_datasets(sources, tmp_path, hand, adv, domain)


def test_fingerprint_ignores_order_but_not_content() -> None:
    a = [Example("x", 0, "s"), Example("y", 1, "s")]
    assert fingerprint(a) == fingerprint(list(reversed(a)))
    assert fingerprint(a) != fingerprint([Example("x", 1, "s"), Example("y", 1, "s")])


def test_real_recruiter_eval_is_legit_and_disjoint_from_training() -> None:
    rows = read_jsonl(RECRUITER_EVAL_PATH, "recruiter_eval")
    assert len(rows) == 50 and {e.label for e in rows} == {0}
    train_texts = {e.text for e in read_jsonl(HANDWRITTEN_PATH, "handwritten")}
    assert not ({e.text for e in rows} & train_texts)
    assert any(" tes " in f" {e.text} " for e in rows) and any("your" in e.text for e in rows)
