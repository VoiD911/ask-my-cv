import copy
import json
from datetime import date

import pytest

from tools.devlog import issues
from tools.devlog.redact import RedactConfig, SecretDetected


def journal():
    event = {
        "date": "2026-09-25T12:00:00Z",
        "type": "implementation",
        "description": "Implemented task",
        "verdict": None,
        "commits": [],
    }
    return {
        "version": 1,
        "repository": issues.REPOSITORY,
        "plans": [
            {
                "id": "1a",
                "plan_doc": "docs/plans/1a.md",
                "tasks": [
                    {"label": "Tâches 1-2", "events": [event]},
                    {
                        "label": "Tâche 2",
                        "events": [{**event, "type": "review", "verdict": "approuvé"}],
                    },
                    {"label": "Revue finale", "events": [event]},
                    {"label": "Hors tâche", "events": [event]},
                ],
            }
        ],
    }


def build(data):
    return issues.build_issues(data, RedactConfig.empty(), reconstructed=date(2026, 9, 28))


def test_real_tasks_merge_overlapping_groups():
    result = build(journal())
    assert [i["title"] for i in result] == ["1a · Tâche 1", "1a · Tâche 2"]
    assert "verdict : approuvé" in result[1]["body"]
    assert "source : Tâches 1-2" in result[0]["body"]
    assert all(i["state"] == "closed" for i in result)
    assert result[0]["labels"] == ["historique", "plan:1a"]
    assert build(journal()) == result


def test_github_flow_plans_get_no_historical_issue():
    data = journal()
    other = copy.deepcopy(data["plans"][0])
    other["id"] = "1e-2d"
    data["plans"].append(other)
    result = issues.build_issues(
        data, RedactConfig.empty(), reconstructed=date(2026, 9, 28), skip_plans=frozenset({"1e-2d"})
    )
    assert [i["title"] for i in result] == ["1a · Tâche 1", "1a · Tâche 2"]


def test_subtask_labels_get_no_historical_issue():
    data = journal()
    data["plans"][0]["tasks"].append({"label": "Tâche 4b", "events": [{"date": "x"}]})
    assert [i["title"] for i in build(data)] == ["1a · Tâche 1", "1a · Tâche 2"]


def test_report_summary_is_masked_in_issue():
    data = journal()
    data["plans"][0]["tasks"][0]["events"][0]["summary"] = "Fixed problem for user@private.invalid"
    body = build(data)[0]["body"]
    assert "Fixed problem" in body
    assert "user@private.invalid" not in body


def test_private_text_masked_and_secret_blocks_entire_batch():
    data = journal()
    data["plans"][0]["tasks"][0]["events"][0]["description"] = "contact person@private.invalid"
    assert "person@private.invalid" not in json.dumps(build(data))
    data["plans"][0]["tasks"][1]["events"][0]["description"] = "ghp_" + "aB3x" * 9
    with pytest.raises(SecretDetected):
        build(data)


@pytest.mark.parametrize(
    "field,value", [("id", "../bad"), ("plan_doc", "https://example.com/evil")]
)
def test_untrusted_paths_rejected(field, value):
    data = journal()
    data["plans"][0][field] = value
    with pytest.raises(ValueError):
        build(data)


def test_apply_paginates_skips_closed_and_resumes_open(monkeypatch):
    desired = build(journal())
    calls = []

    def gh(*args, payload=None):
        calls.append((args, payload))
        if "--paginate" in args:
            return json.dumps(
                [
                    [{"title": desired[0]["title"], "number": 7, "state": "closed"}],
                    [{"title": desired[1]["title"], "number": 8, "state": "open"}],
                ]
            )
        return "{}"

    monkeypatch.setattr(issues, "_gh", gh)
    issues.apply_issues(desired)
    assert not any("POST" in args for args, _ in calls)
    patches = [(args, payload) for args, payload in calls if "PATCH" in args]
    assert len(patches) == 1
    assert patches[0][0][1].endswith("/8")
    assert patches[0][1] == {"state": "closed"}


def test_new_issues_created_then_closed(monkeypatch):
    calls = []

    def gh(*args, payload=None):
        calls.append((args, copy.deepcopy(payload)))
        if "--paginate" in args:
            return "[[]]"
        if "POST" in args:
            return '{"number": 42, "state": "open"}'
        return "{}"

    monkeypatch.setattr(issues, "_gh", gh)
    issues.apply_issues(build(journal())[:1])
    mutations = [(args, payload) for args, payload in calls if "--method" in args]
    assert "POST" in mutations[0][0]
    assert "PATCH" in mutations[1][0]


def test_default_cli_has_no_github_calls(tmp_path, monkeypatch, capsys):
    path = tmp_path / "index.json"
    path.write_text(json.dumps(journal()), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["issues", "--index", str(path), "--date", "2026-09-28"])
    monkeypatch.setattr(issues, "load_config", lambda **kwargs: RedactConfig.empty())
    monkeypatch.setattr(
        issues, "_gh", lambda *args, **kwargs: pytest.fail("unexpected GitHub call")
    )
    assert issues.main() == 0
    assert len(json.loads(capsys.readouterr().out)) == 2
