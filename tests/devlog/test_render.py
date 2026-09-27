"""Tests du rendu du journal public (`tools/devlog/render.py`) et de sa CLI.

Toutes les données sont synthétiques : agents, plans, SHA, comptes AWS et
chemins sont inventés. Les chaînes ressemblant à des secrets sont construites
par concaténation à l'exécution, pour qu'aucun scanner ne voie une fuite dans
ce fichier. Aucun journal réel n'est lu.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from tools.devlog.__main__ import main
from tools.devlog.extract import AgentRecord, PlanWindow
from tools.devlog.redact import RedactConfig, SecretDetected
from tools.devlog.render import (
    FINAL_REVIEW,
    OFF_TASK,
    PlanDoc,
    RenderResult,
    load_plan_docs,
    load_plan_windows,
    render,
    task_key,
    verdict,
)

FAKE_ACCOUNT_ID = "111122223333"
CONFIG = RedactConfig(aws_account_ids=frozenset({FAKE_ACCOUNT_ID}))
REPO_URL = "https://github.com/VoiD911/ask-my-cv"


def _sha(seed: str) -> str:
    return sha256(seed.encode()).hexdigest()[:40]


OLD_SHA = _sha("ancien-commit")
NEW_SHA = _sha("nouveau-commit")
LATER_SHA = _sha("commit-posterieur")
COMMIT_MAP = {OLD_SHA: NEW_SHA}
PUBLISHED = frozenset({NEW_SHA, LATER_SHA})


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def _record(**overrides: object) -> AgentRecord:
    base = AgentRecord(
        id="a0",
        type="general-purpose",
        model="demo-model",
        description="Implement Task 1: demo",
        started=_dt("2026-03-02T09:00:00"),
        ended=_dt("2026-03-02T10:00:00"),
        prompt="",
        report="Rapport de démonstration.",
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def _doc(
    plan_id: str,
    start: str,
    end: str | None,
    *,
    title: str | None = None,
    goal: str = "Objectif fictif.",
) -> PlanDoc:
    window = PlanWindow(
        plan_id,
        _dt(start),
        _dt(end) if end else None,
        (plan_id, f"plan {plan_id}"),
    )
    return PlanDoc(
        window=window,
        title=title or f"Plan {plan_id} fictif",
        goal=goal,
        filename=f"{start[:10]}-ask-my-cv-{plan_id}-demo.md",
    )


DOCS = [
    _doc("9a", "2026-03-01T00:00:00", "2026-04-01T00:00:00"),
    _doc("9b", "2026-04-01T00:00:00", None),
]


def _render(agents: list[AgentRecord], **kwargs: object) -> RenderResult:
    return render(agents, DOCS, COMMIT_MAP, PUBLISHED, CONFIG, **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Plans
# --------------------------------------------------------------------------


def _write_plan(directory: Path, name: str, title: str, goal: str) -> None:
    (directory / name).write_text(f"{title}\n\n> Note\n\n{goal}\n\n## Suite\n", encoding="utf-8")


def test_load_plan_docs_parses_ids_windows_titles_and_goals(tmp_path: Path) -> None:
    _write_plan(tmp_path, "2026-01-05-ask-my-cv-1b-rag-core.md", "# Plan 1b", "**Goal:** Cœur.")
    _write_plan(tmp_path, "2026-01-09-ask-my-cv-1b-bis-hardening.md", "# Bis", "**Goal:** Durcir.")
    _write_plan(tmp_path, "2026-01-12-ask-my-cv-1c-1a-infra.md", "# 1c-1a", "**Goal:** Infra.")
    _write_plan(tmp_path, "2026-01-12-ask-my-cv-1c-2-deploy.md", "# 1c-2", "**Goal:** Déployer.")
    _write_plan(tmp_path, "2026-01-20-ask-my-cv-1d-3-2fa.md", "# 1d-3", "**Goal:** Sécurité.")
    _write_plan(tmp_path, "2026-02-01-ask-my-cv-1e-2b-archive.md", "# 1e-2b", "**Goal:** Archive.")
    (tmp_path / "README.md").write_text("# pas un plan\n", encoding="utf-8")

    docs = load_plan_docs(tmp_path)

    assert [d.window.id for d in docs] == ["1b", "1b-bis", "1c-1a", "1c-2", "1d-3", "1e-2b"]
    by_id = {d.window.id: d for d in docs}
    assert by_id["1b"].window.start == _dt("2026-01-05T00:00:00")
    assert by_id["1b"].window.end == _dt("2026-01-09T00:00:00")
    # Deux plans le même jour : même fenêtre, jusqu'à la date distincte suivante.
    assert by_id["1c-1a"].window.start == by_id["1c-2"].window.start == _dt("2026-01-12T00:00:00")
    assert by_id["1c-1a"].window.end == by_id["1c-2"].window.end == _dt("2026-01-20T00:00:00")
    assert by_id["1e-2b"].window.end is None
    assert "1b-bis" in by_id["1b-bis"].window.keywords
    assert "plan 1b-bis" in by_id["1b-bis"].window.keywords
    assert by_id["1b-bis"].title == "Bis"
    assert by_id["1b-bis"].goal == "Durcir."
    assert by_id["1d-3"].filename == "2026-01-20-ask-my-cv-1d-3-2fa.md"
    assert [w.id for w in load_plan_windows(tmp_path)] == [d.window.id for d in docs]


# --------------------------------------------------------------------------
# Tâches
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Implement Task 12: SSE API", "Tâche 12"),
        ("Review Tasks 8-9 spec+quality", "Tâches 8-9"),
        ("Plan 1c-1b Task 4 DynamoDB ledger", "Tâche 4"),
        ("Implement 1e-1 task 5 (chat, page, e2e)", "Tâche 5"),
        ("Fix task 2 review minors", "Tâche 2"),
        ("Final review plan 1d-3", FINAL_REVIEW),
        ("Revue finale du plan 1e-1", FINAL_REVIEW),
        ("Review PR #11 Lighthouse", OFF_TASK),
        ("Restore domain FPR 0, tighten dup test", OFF_TASK),
        ("Tâche 0 : squelette", "Tâche 0"),
        ("Revue tâches 3-4", "Tâches 3-4"),
        ("Plan 1c-1b demo", OFF_TASK),
    ],
)
def test_task_key_from_description(description: str, expected: str) -> None:
    assert task_key(_record(description=description, prompt="")) == expected


def test_task_key_falls_back_to_prompt_head() -> None:
    record = _record(description="Implement ledger", prompt="You are implementing Task 7 of …")
    assert task_key(record) == "Tâche 7"
    far = _record(description="Implement ledger", prompt="x" * 500 + " Task 7")
    assert task_key(far) == OFF_TASK


# --------------------------------------------------------------------------
# Verdict
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        ("Tout est propre.\n\nVerdict: Approved.", "approuvé"),
        ("Rien à signaler ; my verdict is Approved", "approuvé"),
        ("**Verdict : Approuvé**", "approuvé"),
        ("Verdict: ready to push", "approuvé"),
        ("Verdict: Needs fixes (2 importants)", "corrections demandées"),
        ("Verdict: not ready to push yet", "corrections demandées"),
        ("Findings…\n\nApproved\n", "approuvé"),
        ("**Verdict**\n\nChanges requested.", "corrections demandées"),
        ("Verdict : changements demandés", "corrections demandées"),
        ("Verdict: approved once the fixes land — needs fixes first", "corrections demandées"),
        ("Aucune conclusion ici.", "non déterminé"),
        ("", "non déterminé"),
    ],
)
def test_verdict(report: str, expected: str) -> None:
    assert verdict(report) == expected


def test_verdict_prefers_the_verdict_sentence_over_the_body() -> None:
    report = "Earlier draft needed fixes, now resolved.\n\nVerdict: Approved."
    assert verdict(report) == "approuvé"


# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------


def test_render_masks_account_ids_and_user_paths() -> None:
    report = f"Déployé sur le compte {FAKE_ACCOUNT_ID} depuis C:\\Users\\alice\\proj\\app.py."
    result = _render([_record(report=report)])
    journal = result.files["9a.md"]
    assert FAKE_ACCOUNT_ID not in journal
    assert "alice" not in journal
    assert "<compte-aws>" in journal
    assert "~\\proj\\app.py" in journal


def test_render_aborts_on_secret_and_produces_nothing() -> None:
    fake_key = "sk-" + "lf-" + "0123456789abcdef" * 2
    agents = [_record(id="ok"), _record(id="bad", report=f"clé : {fake_key}")]
    with pytest.raises(SecretDetected) as excinfo:
        _render(agents)
    assert fake_key not in str(excinfo.value)


def test_secret_in_description_also_aborts() -> None:
    fake_key = "gh" + "p_" + "A1b2C3d4E5" * 4
    with pytest.raises(SecretDetected):
        _render([_record(description=f"Implement Task 1 {fake_key}")])


def test_prompts_are_never_published() -> None:
    prompt = "CONSIGNE-SECRETE-DU-CONTROLEUR : implement Task 3 carefully"
    result = _render([_record(description="Implement ledger", prompt=prompt)])
    for content in result.files.values():
        assert "CONSIGNE-SECRETE" not in content
    assert "## Tâche 3" in result.files["9a.md"]


def test_agent_ids_are_not_published() -> None:
    result = _render([_record(id="agentid0123456789")])
    for content in result.files.values():
        assert "agentid0123456789" not in content


def test_unknown_agents_are_excluded_and_reported() -> None:
    lost = _record(id="lost", description="Implement Task 2", started=_dt("2025-01-01T00:00:00"))
    result = _render([_record(id="found"), lost])
    assert [u.agent for u in result.unknown] == ["lost"]
    assert result.unknown[0].description == "Implement Task 2"
    assert result.unknown[0].date == "2025-01-01 00:00"
    assert "Tâche 2" not in result.files["9a.md"]
    assert set(result.files) == {"9a.md", "index.json"}


def test_assignments_override_assign_plan() -> None:
    lost = _record(id="lost", description="Implement Task 2", started=_dt("2025-01-01T00:00:00"))
    moved = _record(id="moved", description="Implement Task 5")
    result = _render([lost, moved], assignments={"lost": "9b", "moved": "9b"})
    assert result.unknown == []
    assert set(result.files) == {"9b.md", "index.json"}
    assert "## Tâche 2" in result.files["9b.md"]
    assert "## Tâche 5" in result.files["9b.md"]


def test_assignment_to_an_unknown_plan_is_rejected() -> None:
    with pytest.raises(ValueError, match="zz"):
        _render([_record()], assignments={"a0": "zz"})


def test_old_sha_is_translated_and_linked() -> None:
    report = f"Commit {OLD_SHA} poussé, puis {LATER_SHA}."
    journal = _render([_record(report=report)]).files["9a.md"]
    assert OLD_SHA not in journal
    assert f"{REPO_URL}/commit/{NEW_SHA}" in journal
    assert f"{REPO_URL}/commit/{LATER_SHA}" in journal


def test_pr_links_only_for_github_flow_plans() -> None:
    agents = [_record(description="Review PR #11 Lighthouse", report="Voir issue #16 et PR #12.")]
    plain = _render(agents)
    assert f"{REPO_URL}/pull/" not in plain.files["9a.md"]
    flow = _render(agents, github_flow_plans=frozenset({"9a"}))
    journal = flow.files["9a.md"]
    assert f"{REPO_URL}/pull/11" in journal
    assert f"{REPO_URL}/pull/12" in journal
    assert f"{REPO_URL}/issues/16" in journal
    index = json.loads(flow.files["index.json"])
    links = index["plans"][0]["tasks"][0]["events"][0]["links"]
    assert links == [f"{REPO_URL}/pull/11", f"{REPO_URL}/issues/16", f"{REPO_URL}/pull/12"]


def test_journal_structure_and_ordering() -> None:
    agents = [
        _record(id="c", description="Final review plan 9a", started=_dt("2026-03-09T09:00:00")),
        _record(id="b", description="Review Task 10", report="Verdict: Approved."),
        _record(id="a", description="Implement Task 10", started=_dt("2026-03-02T08:00:00")),
        _record(id="d", description="Implement Tasks 2-3"),
        _record(
            id="e", description="Fix task 10 review minors", started=_dt("2026-03-03T09:00:00")
        ),
        _record(id="f", description="Restore domain FPR 0"),
        _record(id="g", description="Implement Task 0: scaffold"),
    ]
    journal = _render(agents).files["9a.md"]
    headings = [line for line in journal.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Tâche 0",
        "## Tâches 2-3",
        "## Tâche 10",
        f"## {FINAL_REVIEW}",
        f"## {OFF_TASK}",
    ]
    assert journal.startswith("# Plan 9a fictif\n")
    assert "Objectif fictif." in journal
    assert "(../plans/2026-03-01-ask-my-cv-9a-demo.md)" in journal
    task10 = journal.split("\n## Tâche 10", 1)[1].split("\n## ", 1)[0]
    assert task10.index("### Implémentation") < task10.index("### Revues")
    assert task10.index("### Revues") < task10.index("### Corrections")
    assert "approuvé" in task10
    assert "2026-03-02 08:00" in task10
    assert "\n<details><summary>Rapport</summary>\n\n" in journal
    assert "\n\n</details>\n" in journal


def test_events_sorted_by_start_then_id() -> None:
    same = _dt("2026-03-02T09:00:00")
    agents = [
        _record(id="z", description="Implement Task 1 (z)", started=same),
        _record(id="y", description="Implement Task 1 (y)", started=same),
        _record(id="x", description="Implement Task 1 (x)", started=_dt("2026-03-02T11:00:00")),
    ]
    journal = _render(agents).files["9a.md"]
    assert journal.index("(y)") < journal.index("(z)") < journal.index("(x)")


def test_unbalanced_code_fence_in_report_is_closed() -> None:
    journal = _render([_record(report="```python\nprint(1)\n")]).files["9a.md"]
    body = journal.split("<details><summary>Rapport</summary>", 1)[1].split("</details>", 1)[0]
    assert body.count("```") % 2 == 0


def test_render_is_deterministic() -> None:
    agents = [
        _record(id="b", description="Review Task 1", report="Verdict: Approved."),
        _record(id="a", report=f"commit {OLD_SHA}"),
    ]
    assert _render(agents).files == _render(list(reversed(agents))).files


def test_suspects_are_reported_without_raw_value() -> None:
    token = "Zq8" + "xT2vLm9" * 7
    result = _render([_record(report=f"jeton opaque {token}")])
    assert result.suspects
    suspect = result.suspects[0]
    assert suspect.plan == "9a"
    assert suspect.task == "Tâche 1"
    assert suspect.agent == "a0"
    assert suspect.description == "Implement Task 1: demo"
    assert token not in json.dumps([s.__dict__ for s in result.suspects])


def test_index_json_schema() -> None:
    agents = [
        _record(id="a", description="Implement Task 1", report=f"commit {OLD_SHA}"),
        _record(id="b", description="Review Task 1", report="Verdict: Needs fixes"),
    ]
    raw = _render(agents).files["index.json"]
    assert raw.endswith("}\n")
    index = json.loads(raw)
    assert list(index) == ["version", "repository", "plans"]
    assert index["version"] == 1
    assert index["repository"] == "VoiD911/ask-my-cv"
    (plan,) = index["plans"]
    assert list(plan) == ["id", "title", "goal", "plan_doc", "journal", "tasks"]
    assert plan["id"] == "9a"
    assert plan["plan_doc"] == "docs/plans/2026-03-01-ask-my-cv-9a-demo.md"
    assert plan["journal"] == "docs/journal/9a.md"
    (task,) = plan["tasks"]
    assert task["label"] == "Tâche 1"
    impl, review = task["events"]
    assert list(impl) == [
        "type",
        "date",
        "agent_type",
        "model",
        "description",
        "verdict",
        "commits",
        "links",
    ]
    assert impl["type"] == "implementation"
    assert impl["verdict"] is None
    assert impl["commits"] == [NEW_SHA]
    assert impl["date"] == "2026-03-02T09:00:00Z"
    assert review["type"] == "review"
    assert review["verdict"] == "corrections demandées"
    assert review["links"] == []


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _write_agent(directory: Path, agent_id: str, description: str, report: str) -> None:
    entries = [
        {
            "type": "user",
            "timestamp": "2026-03-02T09:00:00Z",
            "message": {"role": "user", "content": "consigne fictive"},
        },
        {
            "type": "assistant",
            "timestamp": "2026-03-02T09:30:00Z",
            "message": {"role": "assistant", "content": [{"type": "text", "text": report}]},
        },
    ]
    (directory / f"agent-{agent_id}.jsonl").write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8"
    )
    meta = {"agentType": "general-purpose", "description": description, "model": "demo"}
    (directory / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


@pytest.fixture
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*git, "init", "-q"], check=True)  # noqa: S603
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], check=True)  # noqa: S603
    subagents = tmp_path / "subagents"
    subagents.mkdir()
    _write_agent(subagents, "a1", "Implement Task 1: demo", f"compte {FAKE_ACCOUNT_ID}")
    plans = tmp_path / "plans"
    plans.mkdir()
    _write_plan(plans, "2026-03-01-ask-my-cv-9a-demo.md", "# Plan 9a", "**Goal:** Démo.")
    commit_map = tmp_path / "commit-map"
    commit_map.write_text(f"old new\n{OLD_SHA} {NEW_SHA}\n", encoding="utf-8")
    monkeypatch.setenv("DEVLOG_REDACT_AWS_ACCOUNT_IDS", FAKE_ACCOUNT_ID)
    return {
        "repo": repo,
        "subagents": subagents,
        "plans": plans,
        "commit_map": commit_map,
        "private": tmp_path / "private",
    }


def _cli_args(env: dict[str, Path], report: Path) -> list[str]:
    return [
        "render",
        "--subagents",
        str(env["subagents"]),
        "--commit-map",
        str(env["commit_map"]),
        "--plans-dir",
        str(env["plans"]),
        "--out",
        str(env["repo"] / "docs" / "journal"),
        "--repo",
        str(env["repo"]),
        "--report",
        str(report),
    ]


def test_cli_renders_and_writes_private_report(
    cli_env: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    report = cli_env["private"] / "render-report.json"
    assert main(_cli_args(cli_env, report)) == 0
    out = cli_env["repo"] / "docs" / "journal"
    journal = (out / "9a.md").read_text(encoding="utf-8")
    assert FAKE_ACCOUNT_ID not in journal
    assert (out / "index.json").is_file()
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["unknown"] == []
    assert isinstance(data["suspects"], list)
    printed = capsys.readouterr().out
    assert "9a" in printed


def test_cli_refuses_report_inside_repo(cli_env: dict[str, Path]) -> None:
    report = cli_env["repo"] / "render-report.json"
    assert main(_cli_args(cli_env, report)) != 0
    assert not report.exists()
    assert not (cli_env["repo"] / "docs").exists()


def test_cli_secret_exits_2_without_echo_or_files(
    cli_env: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    fake_key = "sk-" + "lf-" + "fedcba9876543210" * 2
    _write_agent(cli_env["subagents"], "a2", "Implement Task 2", f"clé {fake_key}")
    report = cli_env["private"] / "render-report.json"
    assert main(_cli_args(cli_env, report)) == 2
    captured = capsys.readouterr()
    assert fake_key not in captured.out + captured.err
    assert not (cli_env["repo"] / "docs").exists()
    assert not report.exists()
