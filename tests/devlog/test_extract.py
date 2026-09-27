"""Tests de l'extraction et du rattachement (`tools/devlog/extract.py`).

Les fixtures de `tests/devlog/fixtures/` sont **synthétiques** : elles
reproduisent la structure des journaux de sous-agents (entrées `user` /
`assistant` / `attachment`, blocs `text`, `thinking`, `tool_use`,
`tool_result`, fichiers `.meta.json`) avec un contenu inventé. Les SHA de la
table de correspondance sont eux aussi fictifs.
"""

from __future__ import annotations

import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools.devlog.extract import (
    UNKNOWN,
    UNPUBLISHED_SUFFIX,
    AgentRecord,
    PlanWindow,
    assign_plan,
    load_agent,
    load_agents,
    load_commit_map,
    load_published_shas,
    role,
    translate_shas,
)

FIXTURES = Path(__file__).parent / "fixtures"
SUBAGENTS = FIXTURES / "subagents"


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def _record(**overrides: object) -> AgentRecord:
    base = AgentRecord(
        id="x",
        type="general-purpose",
        model="demo",
        description="",
        started=_dt("2026-01-10T09:00:00"),
        ended=_dt("2026-01-10T10:00:00"),
        prompt="",
        report="",
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def agents() -> dict[str, AgentRecord]:
    return {r.id: r for r in load_agents(SUBAGENTS)}


@pytest.fixture(scope="module")
def commit_map() -> dict[str, str]:
    return load_commit_map(FIXTURES / "commit-map")


# --------------------------------------------------------------------------
# load_agents
# --------------------------------------------------------------------------


def test_load_agents_reads_every_agent_sorted_by_start(agents: dict[str, AgentRecord]) -> None:
    ordered = load_agents(SUBAGENTS)
    assert [r.id for r in ordered] == [
        "d4000000000000004",
        "a1000000000000001",
        "b2000000000000002",
        "c3000000000000003",
    ]
    assert set(agents) == {r.id for r in ordered}


def test_load_agent_fields_from_meta_and_entries(agents: dict[str, AgentRecord]) -> None:
    rec = agents["a1000000000000001"]
    assert rec.type == "general-purpose"
    assert rec.model == "demo-model-large"
    assert rec.description == "Implement demo-a task 1: widget parser"
    assert rec.started == _dt("2026-01-10T09:00:00")
    # La dernière entrée (une pièce jointe) fixe la date de fin.
    assert rec.ended == datetime(2026, 1, 10, 9, 45, 1, tzinfo=UTC)
    assert rec.prompt.startswith("You are an implementer subagent for plan demo-a")


def test_prompt_ignores_meta_messages_and_tool_results(agents: dict[str, AgentRecord]) -> None:
    rec = agents["a1000000000000001"]
    assert "Relance fictive" not in rec.prompt
    assert "def parse" not in rec.prompt


def test_report_is_last_assistant_text_block(agents: dict[str, AgentRecord]) -> None:
    assert agents["a1000000000000001"].report == (
        "Rapport final : parseur livré au commit abc1234, tests verts."
    )


def test_prompt_given_as_text_blocks(agents: dict[str, AgentRecord]) -> None:
    assert agents["b2000000000000002"].prompt.startswith("Please look at commit abc1234")


def test_model_falls_back_to_first_real_assistant_model(agents: dict[str, AgentRecord]) -> None:
    # Méta sans `model` ; le premier message est « <synthetic> » et doit être ignoré.
    assert agents["b2000000000000002"].model == "demo-model-small"


def test_agent_without_final_text_has_empty_report(agents: dict[str, AgentRecord]) -> None:
    assert agents["d4000000000000004"].report == ""


def test_missing_meta_uses_placeholders(tmp_path: Path) -> None:
    src = SUBAGENTS / "agent-c3000000000000003.jsonl"
    dst = tmp_path / "agent-e5000000000000005.jsonl"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    rec = load_agent(dst)
    assert rec.id == "e5000000000000005"
    assert rec.type == UNKNOWN
    assert rec.description == ""
    assert rec.model == "demo-model-large"


def test_invalid_json_line_raises_with_location(tmp_path: Path) -> None:
    bad = tmp_path / "agent-f6.jsonl"
    bad.write_text('{"type": "user", "timestamp": "2026-01-01T00:00:00.000Z"}\n{oops\n')
    with pytest.raises(ValueError, match=r"agent-f6\.jsonl:2"):
        load_agent(bad)


def test_file_without_timestamps_raises(tmp_path: Path) -> None:
    empty = tmp_path / "agent-f7.jsonl"
    empty.write_text("\n")
    with pytest.raises(ValueError, match="aucune entrée horodatée"):
        load_agent(empty)


# --------------------------------------------------------------------------
# role
# --------------------------------------------------------------------------


def test_role_of_fixture_agents(agents: dict[str, AgentRecord]) -> None:
    assert role(agents["a1000000000000001"]) == "implementation"
    assert role(agents["b2000000000000002"]) == "review"  # type *reviewer*
    assert role(agents["c3000000000000003"]) == "fix"
    assert role(agents["d4000000000000004"]) == "other"


@pytest.mark.parametrize(
    ("description", "prompt", "expected"),
    [
        ("Implement task 3", "", "implementation"),
        ("Task 3 spec compliance review", "", "review"),
        ("Quality review task 3", "", "review"),
        ("Final review of the branch", "", "review"),
        ("Re-review task 3 after fixes", "", "review"),
        ("Rereview task 3", "", "review"),
        ("Fix review findings on task 3", "", "fix"),
        ("Address reviewer comments", "", "fix"),
        ("Review the fix for task 3", "", "review"),
        ("Revue de la tâche 3", "", "review"),
        ("Correctifs de la tâche 3", "", "fix"),
        ("", "You are an implementer subagent. The PR is under review.", "implementation"),
        ("", "You are reviewing the implementation of task 2.", "review"),
        ("Survey the repo", "List the modules.", "other"),
    ],
)
def test_role_from_description_then_prompt(description: str, prompt: str, expected: str) -> None:
    assert role(_record(description=description, prompt=prompt)) == expected


def test_role_prompt_is_only_read_at_its_start() -> None:
    prompt = "Survey the repo. " + "x " * 300 + "then implement everything."
    assert role(_record(prompt=prompt)) == "other"


def test_reviewer_type_wins_over_keywords() -> None:
    rec = _record(type="ecc:security-reviewer", description="Implement nothing, fix nothing")
    assert role(rec) == "review"


# --------------------------------------------------------------------------
# assign_plan
# --------------------------------------------------------------------------

PLANS = (
    PlanWindow("demo-a", _dt("2026-01-01T00:00:00"), _dt("2026-02-01T00:00:00"), ("demo-a",)),
    PlanWindow("demo-b", _dt("2026-02-01T00:00:00"), None, ("demo-b",)),
    PlanWindow("1e-2", _dt("2026-03-01T00:00:00"), _dt("2026-03-10T00:00:00"), ("1e-2",)),
    PlanWindow("1e-2b", _dt("2026-03-05T00:00:00"), _dt("2026-03-20T00:00:00"), ("1e-2b",)),
)


def test_assign_plan_fixture_agents(agents: dict[str, AgentRecord]) -> None:
    assert assign_plan(agents["a1000000000000001"], PLANS) == "demo-a"
    assert (
        assign_plan(agents["b2000000000000002"], PLANS) == "demo-a"
    )  # via la consigne (description muette)
    assert assign_plan(agents["c3000000000000003"], PLANS) == "demo-b"
    assert assign_plan(agents["d4000000000000004"], PLANS) == UNKNOWN  # hors fenêtres


def test_assign_plan_by_date_only() -> None:
    assert assign_plan(_record(started=_dt("2026-01-15T00:00:00")), PLANS) == "demo-a"


def test_assign_plan_window_end_is_exclusive() -> None:
    assert assign_plan(_record(started=_dt("2026-02-01T00:00:00")), PLANS) == "demo-b"


def test_assign_plan_overlapping_windows_without_keyword_is_unknown() -> None:
    assert assign_plan(_record(started=_dt("2026-03-06T00:00:00")), PLANS) == UNKNOWN


def test_assign_plan_overlap_resolved_by_description() -> None:
    rec = _record(started=_dt("2026-03-06T00:00:00"), description="1e-2b task 2")
    assert assign_plan(rec, PLANS) == "1e-2b"
    rec = _record(started=_dt("2026-03-06T00:00:00"), description="Plan 1e-2 final review")
    assert assign_plan(rec, PLANS) == "1e-2"


def test_assign_plan_conflict_between_date_and_description_is_unknown() -> None:
    rec = _record(started=_dt("2026-01-15T00:00:00"), description="demo-b task 1")
    assert assign_plan(rec, PLANS) == UNKNOWN


def test_assign_plan_keyword_outside_any_window() -> None:
    rec = _record(started=_dt("2025-06-01T00:00:00"), description="demo-a leftovers")
    assert assign_plan(rec, PLANS) == "demo-a"


def test_assign_plan_description_takes_precedence_over_prompt() -> None:
    rec = _record(
        started=_dt("2026-03-06T00:00:00"),
        description="1e-2b task 3",
        prompt="Same flow as in 1e-2 …",
    )
    assert assign_plan(rec, PLANS) == "1e-2b"


def test_assign_plan_several_keywords_is_unknown() -> None:
    rec = _record(started=_dt("2025-06-01T00:00:00"), description="Compare demo-a and demo-b")
    assert assign_plan(rec, PLANS) == UNKNOWN


def test_assign_plan_no_plans() -> None:
    assert assign_plan(_record(), ()) == UNKNOWN


# --------------------------------------------------------------------------
# load_commit_map / translate_shas
# --------------------------------------------------------------------------


def test_load_commit_map_skips_header_and_pruned(commit_map: dict[str, str]) -> None:
    assert commit_map["abc1234000000000000000000000000000000001"] == (
        "def5678000000000000000000000000000000001"
    )
    assert "abd0000000000000000000000000000000000003" not in commit_map
    assert len(commit_map) == 4


def test_translate_short_and_long_shas(commit_map: dict[str, str]) -> None:
    text = "Voir abc1234 et abc9999000000000000000000000000000000002."
    assert translate_shas(text, commit_map) == (
        "Voir def5678 et fed8765000000000000000000000000000000002."
    )


def test_translate_keeps_prefix_length(commit_map: dict[str, str]) -> None:
    assert translate_shas("commit abc12340", commit_map) == "commit def56780"


def test_translate_leaves_new_shas_untouched(commit_map: dict[str, str]) -> None:
    text = "commit fed8765 publié"
    assert translate_shas(text, commit_map) == text


def test_translate_marks_unknown_commit_references(commit_map: dict[str, str]) -> None:
    assert translate_shas("commit 9f8e7d6 abandonné", commit_map) == (
        f"commit 9f8e7d6{UNPUBLISHED_SUFFIX} abandonné"
    )
    assert translate_shas("SHA `9f8e7d6c`", commit_map) == f"SHA `9f8e7d6c{UNPUBLISHED_SUFFIX}`"
    full = "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    assert translate_shas(f"voir {full}", commit_map) == f"voir {full}{UNPUBLISHED_SUFFIX}"


def test_translate_marks_pruned_commits(commit_map: dict[str, str]) -> None:
    assert translate_shas("commit abd0000", commit_map) == f"commit abd0000{UNPUBLISHED_SUFFIX}"


def test_translate_oneline_log(commit_map: dict[str, str]) -> None:
    log = "abc1234 feat: parseur\n9f8e7d6 wip abandonné\n- abc9999 fix"
    assert translate_shas(log, commit_map) == (
        f"def5678 feat: parseur\n9f8e7d6{UNPUBLISHED_SUFFIX} wip abandonné\n- fed8765 fix"
    )


def test_translate_ambiguous_prefix_is_left_alone(commit_map: dict[str, str]) -> None:
    assert translate_shas("commit 5555555", commit_map) == "commit 5555555"
    assert translate_shas("commit 5555555a", commit_map) == "commit 6666666a"


@pytest.mark.parametrize(
    "text",
    [
        "sha256:abc1234000000000000000000000000000000001",
        "image@sha256:9f8e7d6c5b4a39281706f5e4d3c2b1a0",
        "id 1b4e28ba-2fa1-11d2-883f-0016d3cca427",
        "agent-a0126fb292b5bfcbb",
        "empreinte deadbeefcafe dans un texte quelconque",
        "abc123",  # trop court
        "xabc1234 abc1234y",  # pas de borne de mot
        "ABC1234",  # majuscules : pas un SHA git
    ],
)
def test_translate_ignores_non_commit_hex(text: str, commit_map: dict[str, str]) -> None:
    assert translate_shas(text, commit_map) == text


def test_translate_github_commit_url(commit_map: dict[str, str]) -> None:
    url = "https://github.com/demo/repo/commit/abc1234000000000000000000000000000000001"
    assert translate_shas(url, commit_map) == (
        "https://github.com/demo/repo/commit/def5678000000000000000000000000000000001"
    )


def test_translate_is_idempotent(commit_map: dict[str, str]) -> None:
    text = "commit abc1234, commit 9f8e7d6, sha256:0123456789abcdef"
    once = translate_shas(text, commit_map)
    assert translate_shas(once, commit_map) == once


def test_translate_on_fixture_report(
    agents: dict[str, AgentRecord], commit_map: dict[str, str]
) -> None:
    assert "def5678" in translate_shas(agents["a1000000000000001"].report, commit_map)


def test_translate_leaves_commits_published_after_the_rewrite(commit_map: dict[str, str]) -> None:
    later = "7a7a7a7000000000000000000000000000000009"
    assert translate_shas("commit 7a7a7a7", commit_map, published={later}) == "commit 7a7a7a7"
    assert translate_shas("commit 7a7a7a7", commit_map) == f"commit 7a7a7a7{UNPUBLISHED_SUFFIX}"


def test_load_published_shas_reads_this_repository() -> None:
    repo = Path(__file__).resolve().parents[2]
    head = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), "rev-parse", "HEAD"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head in load_published_shas(repo)
