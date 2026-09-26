from __future__ import annotations

import json
from pathlib import Path

import boto3
import pytest
from botocore.stub import Stubber

from ml import drift


def test_psi_est_nul_pour_des_distributions_identiques() -> None:
    counts = [1, 2, 3, 4, 5, 5, 4, 3, 2, 1]
    assert drift.psi(counts, counts) == pytest.approx(0.0, abs=1e-9)


def test_psi_est_eleve_pour_des_distributions_tres_differentes() -> None:
    reference = [100, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    production = [0, 0, 0, 0, 0, 0, 0, 0, 0, 100]
    assert drift.psi(reference, production) > 0.25


def test_psi_lisse_les_compartiments_vides_sans_division_par_zero() -> None:
    reference = [10, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    production = [0, 10, 0, 0, 0, 0, 0, 0, 0, 0]
    value = drift.psi(reference, production)
    assert value > 0
    assert value != float("inf")


def test_psi_leve_value_error_si_longueurs_differentes() -> None:
    with pytest.raises(ValueError, match="même longueur"):
        drift.psi([1, 2, 3], [1, 2])


def test_histogram_a_dix_compartiments_sur_0_1() -> None:
    counts = drift.histogram([0.0, 0.05, 0.5, 0.95, 1.0])
    assert len(counts) == 10
    assert sum(counts) == 5


def test_histogram_place_un_score_de_1_dans_le_dernier_compartiment() -> None:
    counts = drift.histogram([1.0])
    assert counts[-1] == 1
    assert sum(counts[:-1]) == 0


def _query_results_response(status: str, rows: list[list[dict[str, str]]]) -> dict:
    return {
        "status": status,
        "results": rows,
        "statistics": {"recordsMatched": 0.0, "recordsScanned": 0.0, "bytesScanned": 0.0},
    }


def test_fetch_scores_interroge_logs_insights_et_renvoie_les_flottants() -> None:
    client = boto3.client("logs", region_name="ca-central-1")
    stub = Stubber(client)
    stub.add_response(
        "start_query",
        {"queryId": "q1"},
        {
            "logGroupName": "aws/spans",
            "startTime": 1000,
            "endTime": 2000,
            "queryString": drift.LOGS_INSIGHTS_QUERY,
        },
    )
    stub.add_response(
        "get_query_results",
        _query_results_response("Running", []),
        {"queryId": "q1"},
    )
    stub.add_response(
        "get_query_results",
        _query_results_response(
            "Complete",
            [
                [{"field": "score", "value": "0.083"}],
                [{"field": "score", "value": "0.5"}],
            ],
        ),
        {"queryId": "q1"},
    )
    sleeps: list[float] = []
    with stub:
        scores = drift.fetch_scores(client, "aws/spans", 1000, 2000, sleep=sleeps.append)
    stub.assert_no_pending_responses()
    assert scores == [0.083, 0.5]
    assert sleeps == [drift.POLL_INTERVAL_S]


def test_fetch_scores_leve_une_exception_si_la_requete_echoue() -> None:
    client = boto3.client("logs", region_name="ca-central-1")
    stub = Stubber(client)
    stub.add_response(
        "start_query",
        {"queryId": "q1"},
        {
            "logGroupName": "aws/spans",
            "startTime": 1000,
            "endTime": 2000,
            "queryString": drift.LOGS_INSIGHTS_QUERY,
        },
    )
    stub.add_response(
        "get_query_results",
        _query_results_response("Failed", []),
        {"queryId": "q1"},
    )
    with stub, pytest.raises(drift.DriftError, match="échouée"):
        drift.fetch_scores(client, "aws/spans", 1000, 2000, sleep=lambda _: None)
    stub.assert_no_pending_responses()


def test_fetch_scores_leve_une_exception_si_le_delai_maximal_est_depasse() -> None:
    client = boto3.client("logs", region_name="ca-central-1")
    stub = Stubber(client)
    stub.add_response(
        "start_query",
        {"queryId": "q1"},
        {
            "logGroupName": "aws/spans",
            "startTime": 1000,
            "endTime": 2000,
            "queryString": drift.LOGS_INSIGHTS_QUERY,
        },
    )
    for _ in range(drift.MAX_POLLS):
        stub.add_response(
            "get_query_results",
            _query_results_response("Running", []),
            {"queryId": "q1"},
        )
    with stub, pytest.raises(drift.DriftError, match="délai"):
        drift.fetch_scores(client, "aws/spans", 1000, 2000, sleep=lambda _: None)
    stub.assert_no_pending_responses()


def _reference_file(tmp_path: Path, counts: list[int]) -> Path:
    path = tmp_path / "metrics.json"
    path.write_text(
        json.dumps({"domain_score_histogram": {"bins": [], "counts": counts}}),
        encoding="utf-8",
    )
    return path


def test_main_signale_des_donnees_insuffisantes(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    reference = _reference_file(tmp_path, [10, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    scores = [0.05] * 10  # < MIN_SAMPLES

    def fetch(client, log_group, start, end, **kwargs):  # noqa: ANN001, ARG001
        return scores

    code = drift.main(
        ["--reference", str(reference), "--days", "7"],
        client_factory=lambda region: object(),
        fetch_scores=fetch,
    )
    assert code == 0
    assert "données insuffisantes" in capsys.readouterr().out


def test_main_echoue_si_psi_haut(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    reference = _reference_file(tmp_path, [100, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    scores = [0.95] * 60

    def fetch(client, log_group, start, end, **kwargs):  # noqa: ANN001, ARG001
        return scores

    code = drift.main(
        ["--reference", str(reference), "--days", "7"],
        client_factory=lambda region: object(),
        fetch_scores=fetch,
    )
    assert code == 1
    out = capsys.readouterr().out
    assert "PSI" in out


def test_main_avertit_si_psi_intermediaire(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    reference = _reference_file(tmp_path, [100, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    scores = [0.01] * 98 + [0.99] * 2
    assert 0.1 <= drift.psi([100, 0, 0, 0, 0, 0, 0, 0, 0, 0], drift.histogram(scores)) < 0.2

    def fetch(client, log_group, start, end, **kwargs):  # noqa: ANN001, ARG001
        return scores

    code = drift.main(
        ["--reference", str(reference), "--days", "7"],
        client_factory=lambda region: object(),
        fetch_scores=fetch,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "::warning::" in out


def test_main_ok_si_psi_bas(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    counts = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10]
    reference = _reference_file(tmp_path, counts)
    scores = []
    for i in range(10):
        scores += [i / 10 + 0.01] * 10

    def fetch(client, log_group, start, end, **kwargs):  # noqa: ANN001, ARG001
        return scores

    code = drift.main(
        ["--reference", str(reference), "--days", "7"],
        client_factory=lambda region: object(),
        fetch_scores=fetch,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "::warning::" not in out
