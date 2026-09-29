import re
import statistics
from functools import cache
from pathlib import Path

import pytest

from ml import job_ads, job_ads_compose, job_ads_en, job_ads_fr
from ml.dataset import (
    AD_SHINGLE_NGRAM,
    JOB_ADS_EVAL_PATH,
    NEAR_DUPLICATE_JACCARD,
    JobAdRow,
    near_duplicate_pairs,
    read_job_ads,
)
from ml.job_ads import split_pool


@cache
def rows(split: str) -> tuple[JobAdRow, ...]:
    """Annonces d'évaluation : fichier versionné ; d'entraînement : générées (non versionnées)."""
    if split == "eval":
        return tuple(read_job_ads(JOB_ADS_EVAL_PATH))
    ads = job_ads.generate("train", job_ads.TRAIN_LEGIT, job_ads.TRAIN_INJECTED, job_ads.SEED)
    return tuple(JobAdRow(a.text, a.label, a.injection) for a in ads)


def test_versioned_eval_file_is_exactly_what_the_generator_produces() -> None:
    assert job_ads.main(["--check"]) == 0


def test_generation_writes_the_train_file_and_refuses_a_stale_eval_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    train, evaluation = tmp_path / "train.jsonl", tmp_path / "eval.jsonl"
    monkeypatch.setattr(job_ads, "JOB_ADS_TRAIN_PATH", train)
    monkeypatch.setattr(job_ads, "JOB_ADS_EVAL_PATH", evaluation)
    monkeypatch.setattr(job_ads, "train_jsonl", lambda: "train\n")
    monkeypatch.setattr(job_ads, "eval_jsonl", lambda: "eval\n")
    assert job_ads.main([]) == 1 and not train.exists()  # éval absente ou périmée
    assert job_ads.main(["--write-eval"]) == 0
    assert job_ads.main([]) == 0
    assert train.read_text(encoding="utf-8") == "train\n"


def test_split_pool_partitions_without_overlap() -> None:
    pool = tuple(range(10))
    train, evaluation = split_pool(pool, "train"), split_pool(pool, "eval")
    assert set(train) | set(evaluation) == set(pool)
    assert not set(train) & set(evaluation)
    assert split_pool(pool, "eval", every=2) == (1, 3, 5, 7, 9)


def test_no_sentence_pool_is_shared_between_train_and_eval_injections() -> None:
    for lang in ("fr", "en"):
        assert not set(job_ads.injections(lang, "train")) & set(job_ads.injections(lang, "eval"))


def test_phrase_banks_have_no_duplicates() -> None:
    for bank in (job_ads_fr, job_ads_en, job_ads_compose):
        for name in dir(bank):
            pool = getattr(bank, name)
            if name.isupper() and isinstance(pool, tuple) and pool and isinstance(pool[0], str):
                assert len(pool) == len(set(pool)), f"{bank.__name__}.{name}"


def test_files_have_the_expected_label_counts() -> None:
    for split, (legit, injected) in {
        "train": (job_ads.TRAIN_LEGIT, job_ads.TRAIN_INJECTED),
        "eval": (job_ads.EVAL_LEGIT, job_ads.EVAL_INJECTED),
    }.items():
        data = rows(split)
        assert sum(r.label == 0 for r in data) == legit
        assert sum(r.label == 1 for r in data) == injected


def test_long_legit_ads_are_well_represented() -> None:
    for split, minimum in (("train", 80), ("eval", 30)):
        lengths = [len(r.text) for r in rows(split) if r.label == 0]
        assert max(lengths) >= 7_000, split
        assert sum(n >= 4_000 for n in lengths) >= minimum, split
        assert min(lengths) < 1_000, split  # et des annonces courtes, en une ou deux fenêtres


def test_injection_is_a_single_small_part_of_the_ad() -> None:
    for split in ("train", "eval"):
        injected = [r for r in rows(split) if r.label == 1]
        pool = [*job_ads.injections("fr", split), *job_ads.injections("en", split)]
        for row in injected:
            assert row.injection in pool
            assert sum(p in row.text for p in pool) == 1
        shares = [len(r.injection or "") / len(r.text) for r in injected]
        assert statistics.median(shares) < 0.1


def test_no_near_duplicate_ads_within_a_file() -> None:
    for split in ("train", "eval"):
        texts = [r.text for r in rows(split)]
        pairs = near_duplicate_pairs(texts, texts, NEAR_DUPLICATE_JACCARD, AD_SHINGLE_NGRAM)
        assert [(i, j) for i, j, _ in pairs if i < j] == [], split


def test_no_near_duplicate_between_train_and_eval_ads() -> None:
    train = [r.text for r in rows("train")]
    evaluation = [r.text for r in rows("eval")]
    assert near_duplicate_pairs(train, evaluation) == []


def test_contact_details_are_fictional() -> None:
    for split in ("train", "eval"):
        for row in rows(split):
            for phone in re.findall(r"\b\d{3} \d{3}-\d{4}\b", row.text):
                assert phone[4:9] == "555-0", phone
            for email in re.findall(r"[\w.]+@[\w-]+(?:\.[\w-]+)+", row.text):
                assert email.endswith(".example"), email
