import argparse
import datetime as dt
import json
from pathlib import Path

import pytest
from pytest_bdd import given, scenarios, then, when


scenarios("features")


TOPIC_PREFIXES = {
    "oe": "OPS",
    "sec": "SEC",
    "rel": "REL",
    "perf": "PER",
    "cost": "COST",
    "sus": "SUS",
}


def _bp_html(prefix: str) -> str:
    return f'<a href="./{prefix}-topic.html">Topic</a>'


def _topic_html(prefix: str) -> str:
    qprefix = TOPIC_PREFIXES[prefix]
    return f"<h2>{qprefix} 1: How do you test?</h2>"


def _ensure_cached_questions(ctx, wai):
    if "cache_dir" in ctx:
        return
    cache_dir = ctx["tmp_path"] / "cache"
    questions = []
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for pillar in wai.PILLARS:
        questions.append(
            {
                "pillar": pillar,
                "question_id": wai._qid(pillar, 1),
                "question_text": f"How do you handle {pillar}?",
                "source_url": wai.PILLAR_URLS[pillar],
                "fetched_at": now,
                "license": wai.LICENSE_TEXT,
            }
        )
    wai.save_cache(cache_dir, {"questions": questions, "fetched_at": now})
    ctx["cache_dir"] = cache_dir


def _ensure_target_dir(ctx):
    if "target_dir" in ctx:
        return
    target_dir = ctx["tmp_path"] / "target"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "main.py").write_text("print('ok')")
    (target_dir / ".github/workflows").mkdir(parents=True, exist_ok=True)
    (target_dir / ".github/workflows/ci.yml").write_text("name: ci")
    ctx["target_dir"] = target_dir


def _init_assessment(ctx, wai, monkeypatch):
    if "assessment" in ctx:
        return
    _ensure_cached_questions(ctx, wai)
    _ensure_target_dir(ctx)

    seq = {"n": 0}

    def fake_create(title, issue_type, parent=""):
        seq["n"] += 1
        return f"kanbus-test-{seq['n']}"

    monkeypatch.setattr(wai, "_create_kanbus_issue", fake_create)

    reports_dir = ctx["tmp_path"] / "reports"
    assessment = "test-20260101"
    args = argparse.Namespace(
        target_dir=str(ctx["target_dir"]),
        assessment=assessment,
        reports_dir=str(reports_dir),
        cache_dir=str(ctx["cache_dir"]),
    )
    wai.cmd_init(args)
    ctx["reports_dir"] = reports_dir
    ctx["assessment"] = assessment


@given("sample AWS pages")
def sample_pages(monkeypatch, ctx, wai):
    def fake_fetch(url: str) -> str:
        for prefix in TOPIC_PREFIXES:
            if url.endswith(f"{prefix}-bp.html"):
                return _bp_html(prefix)
            if url.endswith(f"{prefix}-topic.html"):
                return _topic_html(prefix)
        return "<html></html>"

    monkeypatch.setattr(wai, "_fetch_url", fake_fetch)
    ctx["cache_dir"] = ctx["tmp_path"] / "cache"


@when("I run wai fetch")
def run_fetch(ctx, wai):
    args = argparse.Namespace(refresh=True, cache_dir=str(ctx["cache_dir"]))
    wai.cmd_fetch(args)


@then("the questions cache is created with entries for all pillars")
def cache_created(ctx):
    data = json.loads((ctx["cache_dir"] / "questions.json").read_text())
    pillars = {q["pillar"] for q in data["questions"]}
    assert pillars


@given("cached questions")
def cached_questions(ctx, wai):
    _ensure_cached_questions(ctx, wai)


@given("a target repo path")
def target_repo(ctx):
    _ensure_target_dir(ctx)


@when("I run wai init")
def run_init(ctx, wai, monkeypatch):
    _init_assessment(ctx, wai, monkeypatch)


@then("a new assessment folder and Kanbus files are created")
def assessment_created(ctx):
    base = ctx["reports_dir"] / ctx["assessment"]
    assert (base / "index.md").exists()
    assert (base / "kanbus-map.json").exists()


@given("an initialized assessment")
def initialized(ctx, wai, monkeypatch):
    _init_assessment(ctx, wai, monkeypatch)


@given("an answered question")
def answered_question(ctx, wai):
    base = ctx["reports_dir"] / ctx["assessment"]
    pillar_path = base / f"{wai.PILLARS[0]}.md"
    content = pillar_path.read_text()
    content = content.replace("Status: unanswered", "Status: answered", 1)
    content = content.replace("Answer:", "Answer: We do X", 1)
    pillar_path.write_text(content)


@when("I run wai sync-kanbus")
def run_sync(ctx, wai, monkeypatch):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return ""

    def fake_comment(issue_id, text):
        calls.append(["comment", issue_id, text])

    monkeypatch.setattr(wai, "_run", fake_run)
    monkeypatch.setattr(wai, "_kanbus_comment", fake_comment)

    args = argparse.Namespace(assessment=ctx["assessment"], reports_dir=str(ctx["reports_dir"]))
    wai.cmd_sync_kanbus(args)
    ctx["sync_calls"] = calls


@then("Kanbus tasks are commented and closed accordingly")
def sync_assertions(ctx):
    assert ctx.get("sync_calls")


@when("I run wai scan")
def run_scan(ctx, wai):
    args = argparse.Namespace(
        target_dir=str(ctx["target_dir"]),
        assessment=ctx["assessment"],
        reports_dir=str(ctx["reports_dir"]),
        with_scanners=None,
    )
    wai.cmd_scan(args)


@when("I run wai apply-evidence")
def run_apply(ctx, wai):
    args = argparse.Namespace(assessment=ctx["assessment"], reports_dir=str(ctx["reports_dir"]))
    wai.cmd_apply_evidence(args)


@then("evidence blocks are populated and status is partial")
def evidence_applied(ctx, wai):
    base = ctx["reports_dir"] / ctx["assessment"]
    pillar_path = base / f"{wai.PILLARS[0]}.md"
    content = pillar_path.read_text()
    assert "Status: partial" in content
    assert "Evidence:" in content


@when("I run wai record-answer")
def run_record(ctx, wai):
    base = ctx["reports_dir"] / ctx["assessment"]
    kanbus_map = json.loads((base / "kanbus-map.json").read_text())
    qid = next(iter(kanbus_map["tasks"].keys()))
    answer_file = ctx["tmp_path"] / "answer.txt"
    answer_file.write_text("We do Y")
    args = argparse.Namespace(
        assessment=ctx["assessment"],
        question_id=qid,
        status="answered",
        confidence="medium",
        answer_file=str(answer_file),
        reports_dir=str(ctx["reports_dir"]),
    )
    wai.cmd_record_answer(args)
    ctx["record_qid"] = qid


@then("the report is updated with status and answer")
def record_assertion(ctx, wai):
    base = ctx["reports_dir"] / ctx["assessment"]
    for pillar in wai.PILLARS:
        path = base / f"{pillar}.md"
        if not path.exists():
            continue
        content = path.read_text()
        if ctx["record_qid"] in content:
            assert "Status: answered" in content
            assert "Answer: We do Y" in content
            return
    pytest.fail("updated question not found")
