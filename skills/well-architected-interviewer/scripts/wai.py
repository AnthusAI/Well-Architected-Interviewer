#!/usr/bin/env python3
import argparse
import datetime as dt
import html as html_mod
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

CACHE_DIR_DEFAULT = os.path.expanduser("~/.cache/well-architected")
CACHE_FILE = "questions.json"
REPORTS_DIR_DEFAULT = "reports"

PILLARS = [
    "operational-excellence",
    "security",
    "reliability",
    "performance-efficiency",
    "cost-optimization",
    "sustainability",
]

AWS_WA_BASE = "https://docs.aws.amazon.com/wellarchitected/latest/framework"
PILLAR_URLS = {
    "operational-excellence": f"{AWS_WA_BASE}/operational-excellence.html",
    "security": f"{AWS_WA_BASE}/security.html",
    "reliability": f"{AWS_WA_BASE}/reliability.html",
    "performance-efficiency": f"{AWS_WA_BASE}/performance-efficiency.html",
    "cost-optimization": f"{AWS_WA_BASE}/cost-optimization.html",
    "sustainability": f"{AWS_WA_BASE}/sustainability.html",
}
BP_PAGES = {
    "operational-excellence": ("oe-bp.html", "oe-"),
    "security": ("sec-bp.html", "sec-"),
    "reliability": ("rel-bp.html", "rel-"),
    "performance-efficiency": ("perf-bp.html", "perf-"),
    "cost-optimization": ("cost-bp.html", "cost-"),
    "sustainability": ("sus-bp.html", "sus-"),
}

LICENSE_TEXT = "CC BY-SA 4.0"
ATTRIBUTION_TEMPLATE = (
    "AWS Well-Architected Framework (c) Amazon.com, Inc. or its affiliates. "
    "Licensed under Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0). "
    "Source: {source_url}"
)

STATUS_VALUES = {"unanswered", "partial", "answered", "needs_human"}
CONFIDENCE_VALUES = {"low", "medium", "high", "n/a"}


class WAIError(Exception):
    pass


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _today_slug(target_dir: Path) -> str:
    name = target_dir.name or "assessment"
    date = dt.date.today().strftime("%Y%m%d")
    return f"{name}-{date}"


def _run(cmd: List[str]) -> str:
    proc = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise WAIError(proc.stderr.strip() or f"Command failed: {' '.join(cmd)}")
    return proc.stdout


def _fetch_url(url: str) -> str:
    try:
        import requests  # type: ignore
    except Exception as exc:
        raise WAIError("requests is required for wai fetch") from exc
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.text


def _normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = text.replace("Â", " ")
    return re.sub(r"\s+", " ", text).strip()


def _parse_questions_from_html(html: str) -> List[Tuple[str, str]]:
    # Extract text from HTML tags naively to avoid heavy deps.
    text = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html_mod.unescape(text)
    text = text.replace("\u00a0", " ").replace("Â", " ")
    lines = [_normalize_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line]

    questions = []
    for line in lines:
        m = re.match(r"^([A-Z]{3,4})\s*(\d+)\s*:\s*(.+)$", line)
        if m:
            prefix, number, qtext = m.groups()
            qid = f"{prefix}-{number}"
            questions.append((qid, qtext.strip()))
            continue
        if line.lower().startswith("question"):
            q = re.sub(r"^question\s*\d*:?\s*", "", line, flags=re.IGNORECASE)
            if q.endswith("?") and len(q) > 10:
                questions.append(("", q))
        elif line.endswith("?") and len(line) > 15:
            questions.append(("", line))

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for qid, qtext in questions:
        key = (qid or qtext).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append((qid, qtext))
    return deduped


def _short_title(question: str) -> str:
    title = question.strip()
    if len(title) > 80:
        title = title[:77].rstrip() + "..."
    return title


def _qid(pillar: str, idx: int) -> str:
    prefix = pillar.replace("-", "_")[:8]
    return f"{prefix.upper()}-{idx:03d}"


def load_cache(cache_dir: Path) -> Dict:
    path = cache_dir / CACHE_FILE
    if not path.exists():
        raise WAIError("Questions cache not found. Run wai fetch first.")
    return json.loads(_read_text(path))


def save_cache(cache_dir: Path, data: Dict) -> None:
    _ensure_dir(cache_dir)
    _write_text(cache_dir / CACHE_FILE, json.dumps(data, indent=2))


def cmd_fetch(args: argparse.Namespace) -> None:
    cache_dir = Path(args.cache_dir or CACHE_DIR_DEFAULT)
    if cache_dir.exists() and not args.refresh:
        # Still overwrite if file missing
        if (cache_dir / CACHE_FILE).exists():
            print(f"Cache exists at {cache_dir / CACHE_FILE}. Use --refresh to re-fetch.")
            return

    questions = []
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    for pillar, (bp_page, href_prefix) in BP_PAGES.items():
        bp_url = f"{AWS_WA_BASE}/{bp_page}"
        bp_html = _fetch_url(bp_url)
        hrefs = re.findall(rf'href="./({re.escape(href_prefix)}[^"]+\.html)"', bp_html)
        topic_pages = sorted(set(hrefs))
        if not topic_pages:
            continue

        idx = 0
        for page in topic_pages:
            page_url = f"{AWS_WA_BASE}/{page}"
            page_html = _fetch_url(page_url)
            parsed = _parse_questions_from_html(page_html)
            for qid, qtext in parsed:
                idx += 1
                questions.append(
                    {
                        "pillar": pillar,
                        "question_id": qid or _qid(pillar, idx),
                        "question_text": qtext,
                        "source_url": page_url,
                        "fetched_at": fetched_at,
                        "license": LICENSE_TEXT,
                    }
                )

    if not questions:
        raise WAIError("No questions parsed. Check parser heuristics.")

    save_cache(cache_dir, {"questions": questions, "fetched_at": fetched_at})
    print(f"Wrote {len(questions)} questions to {cache_dir / CACHE_FILE}")


def _report_paths(reports_dir: Path, assessment: str) -> Tuple[Path, Path]:
    base = reports_dir / assessment
    return base, base / "index.md"


def _pillar_report_path(base: Path, pillar: str) -> Path:
    return base / f"{pillar}.md"


def _attribution_block(url: str) -> str:
    return ATTRIBUTION_TEMPLATE.format(source_url=url)


def _pillar_header(pillar: str, url: str) -> str:
    return (
        f"# {pillar.replace('-', ' ').title()}\n\n"
        f"> Attribution: {_attribution_block(url)}\n\n"
    )


def _pillar_footer(url: str) -> str:
    return f"\n> Attribution: {_attribution_block(url)}\n"


def _question_block(q: Dict) -> str:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    question_text = _normalize_text(q["question_text"])
    title = _short_title(question_text)
    return (
        f"## {q['question_id']}: {title}\n"
        f"Question: {question_text}\n"
        "Status: unanswered\n"
        "Confidence: n/a\n"
        "Answer:\n"
        "Evidence:\n"
        "Human Questions:\n"
        "Kanbus Task: \n"
        f"Last Updated: {now}\n\n"
    )


def _write_reports(cache: Dict, reports_dir: Path, assessment: str) -> None:
    base, index_path = _report_paths(reports_dir, assessment)
    _ensure_dir(base)

    # Index
    index_lines = [
        f"# Well-Architected Assessment: {assessment}",
        "",
        "## Pillars",
    ]
    for pillar in PILLARS:
        index_lines.append(f"- [{pillar.replace('-', ' ').title()}]({pillar}.md)")
    _write_text(index_path, "\n".join(index_lines) + "\n")

    # Pillars
    questions = cache.get("questions", [])
    for pillar in PILLARS:
        url = PILLAR_URLS[pillar]
        header = _pillar_header(pillar, url)
        blocks = [header]
        for q in questions:
            if q["pillar"] == pillar:
                blocks.append(_question_block(q))
        blocks.append(_pillar_footer(url))
        _write_text(_pillar_report_path(base, pillar), "".join(blocks))


def _create_kanbus_issue(title: str, issue_type: str, parent: str = "") -> str:
    cmd = ["kanbus", "create", title, "--type", issue_type]
    if parent:
        cmd += ["--parent", parent]
    out = _run(cmd)
    match = re.search(r"ID: (kanbus-[\w-]+)", out)
    if not match:
        raise WAIError("Failed to parse Kanbus ID")
    short_id = match.group(1)
    return _resolve_full_id(short_id, title=title, parent=parent)


def _is_full_id(issue_id: str) -> bool:
    return issue_id.count("-") >= 5


def _resolve_full_id(
    short_id: str, title: str = "", parent: str = "", issues: List[Dict] | None = None
) -> str:
    if _is_full_id(short_id):
        return short_id
    if issues is None:
        try:
            snapshot = json.loads(_run(["kanbus", "console", "snapshot"]))
            issues = snapshot.get("issues", [])
        except Exception:
            return short_id
    candidates = [i for i in issues if i.get("id", "").startswith(short_id)]
    if title:
        candidates = [i for i in candidates if i.get("title") == title]
    if parent:
        candidates = [i for i in candidates if i.get("parent") == parent]
    if not candidates:
        return short_id
    candidates.sort(key=lambda i: i.get("created_at") or "")
    return candidates[-1]["id"]


def _kanbus_comment(issue_id: str, text: str) -> None:
    _run(["kanbus", "comment", issue_id, text])


def _kanbus_update_status(issue_id: str, status: str) -> None:
    try:
        _run(["kanbus", "update", issue_id, "--status", status])
    except WAIError as exc:
        msg = str(exc)
        if "no updates requested" in msg:
            return
        raise


def cmd_init(args: argparse.Namespace) -> None:
    target_dir = Path(args.target_dir).resolve()
    if not target_dir.exists():
        raise WAIError("target-dir not found")

    cache_dir = Path(args.cache_dir or CACHE_DIR_DEFAULT)
    cache = load_cache(cache_dir)

    assessment = args.assessment or _today_slug(target_dir)
    reports_dir = Path(args.reports_dir or REPORTS_DIR_DEFAULT)

    _write_reports(cache, reports_dir, assessment)

    # Kanbus structure
    initiative_id = _create_kanbus_issue(f"Well-Architected Assessment: {assessment}", "initiative")
    kanbus_map = {"initiative": initiative_id, "epics": {}, "tasks": {}}

    # Create epics and tasks
    questions = cache.get("questions", [])
    for pillar in PILLARS:
        epic_id = _create_kanbus_issue(f"{pillar.replace('-', ' ').title()} Pillar", "epic", initiative_id)
        kanbus_map["epics"][pillar] = epic_id
        idx = 0
        for q in questions:
            if q["pillar"] != pillar:
                continue
            idx += 1
            title = f"{q['question_id']} { _short_title(q['question_text']) }"
            task_id = _create_kanbus_issue(title, "task", epic_id)
            kanbus_map["tasks"][q["question_id"]] = task_id

    base, _ = _report_paths(reports_dir, assessment)
    _write_text(base / "kanbus-map.json", json.dumps(kanbus_map, indent=2))

    # Inject Kanbus IDs into reports
    _apply_kanbus_ids(base, kanbus_map)


def _parse_questions_from_report(content: str) -> List[Dict]:
    pattern = re.compile(r"^## (?P<id>[^:]+): (?P<title>.*)$", re.MULTILINE)
    entries = []
    for match in pattern.finditer(content):
        start = match.start()
        end = content.find("\n## ", match.end())
        if end == -1:
            end = len(content)
        block = content[start:end]
        entry = _parse_question_block(block)
        entries.append(entry)
    return entries


def _parse_field(block: str, field: str) -> str:
    m = re.search(rf"^{re.escape(field)}:[ \t]*(.*)$", block, re.MULTILINE)
    if not m:
        return ""
    return m.group(1).strip()


def _replace_field(block: str, field: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(field)}:.*$", re.MULTILINE)
    repl = f"{field}: {value}"
    if pattern.search(block):
        return pattern.sub(repl, block)
    return block


def _parse_question_block(block: str) -> Dict:
    lines = block.splitlines()
    header = lines[0]
    qid, title = header[3:].split(": ", 1)
    return {
        "id": qid.strip(),
        "title": title.strip(),
        "question": _parse_field(block, "Question"),
        "status": _parse_field(block, "Status"),
        "confidence": _parse_field(block, "Confidence"),
        "kanbus": _parse_field(block, "Kanbus Task"),
        "block": block,
    }


def _apply_kanbus_ids(base: Path, kanbus_map: Dict) -> None:
    for pillar in PILLARS:
        path = _pillar_report_path(base, pillar)
        if not path.exists():
            continue
        content = _read_text(path)
        new_content = content
        entries = _parse_questions_from_report(content)
        for entry in entries:
            qid = entry["id"]
            task_id = kanbus_map["tasks"].get(qid, "")
            if task_id:
                block = entry["block"]
                block_new = _replace_field(block, "Kanbus Task", task_id)
                new_content = new_content.replace(block, block_new)
        if new_content != content:
            _write_text(path, new_content)


def cmd_scan(args: argparse.Namespace) -> None:
    target_dir = Path(args.target_dir).resolve()
    if not target_dir.exists():
        raise WAIError("target-dir not found")

    reports_dir = Path(args.reports_dir or REPORTS_DIR_DEFAULT)
    base, _ = _report_paths(reports_dir, args.assessment)
    if not base.exists():
        raise WAIError("assessment reports not found")

    evidence = {"inventory": {}, "scanners": {}}

    # Simple inventory
    evidence["inventory"]["languages"] = _detect_languages(target_dir)
    evidence["inventory"]["infra"] = _detect_infra(target_dir)
    evidence["inventory"]["ci"] = _detect_ci(target_dir)

    # Optional scanners
    scanners = []
    if args.with_scanners:
        scanners = [s.strip() for s in args.with_scanners.split(",") if s.strip()]
    for scanner in scanners:
        result = _run_optional_scanner(scanner, target_dir)
        evidence["scanners"][scanner] = result

    _write_text(base / "evidence.json", json.dumps(evidence, indent=2))
    print(f"Wrote evidence to {base / 'evidence.json'}")


def _detect_languages(target_dir: Path) -> List[str]:
    langs = set()
    for path in target_dir.rglob("*"):
        if path.is_dir():
            continue
        ext = path.suffix.lower()
        if ext in {".py", ".js", ".ts", ".go", ".java", ".rb", ".rs"}:
            langs.add(ext)
    return sorted(langs)


def _detect_infra(target_dir: Path) -> List[str]:
    infra = []
    if list(target_dir.rglob("*.tf")):
        infra.append("terraform")
    if list(target_dir.rglob("template.yaml")) or list(target_dir.rglob("template.yml")):
        infra.append("sam")
    if list(target_dir.rglob("serverless.yml")):
        infra.append("serverless")
    if list(target_dir.rglob("helm/*.yaml")):
        infra.append("helm")
    return sorted(set(infra))


def _detect_ci(target_dir: Path) -> List[str]:
    ci = []
    if (target_dir / ".github/workflows").exists():
        ci.append("github-actions")
    if (target_dir / ".gitlab-ci.yml").exists():
        ci.append("gitlab")
    if (target_dir / "Jenkinsfile").exists():
        ci.append("jenkins")
    return sorted(set(ci))


def _run_optional_scanner(scanner: str, target_dir: Path) -> Dict:
    import shutil

    if scanner == "semgrep":
        if not shutil.which("semgrep"):
            return {"status": "missing"}
        out = _run(["semgrep", "--json", "--config", "auto", str(target_dir)])
        return {"status": "ok", "output": json.loads(out)}
    if scanner == "trivy":
        if not shutil.which("trivy"):
            return {"status": "missing"}
        out = _run(["trivy", "fs", "--format", "json", str(target_dir)])
        return {"status": "ok", "output": json.loads(out)}
    return {"status": "unknown_scanner"}


def cmd_apply_evidence(args: argparse.Namespace) -> None:
    reports_dir = Path(args.reports_dir or REPORTS_DIR_DEFAULT)
    base, _ = _report_paths(reports_dir, args.assessment)
    evidence_path = base / "evidence.json"
    if not evidence_path.exists():
        raise WAIError("evidence.json not found. Run wai scan first.")

    evidence = json.loads(_read_text(evidence_path))
    inventory = evidence.get("inventory", {})
    summary_bits = []
    if inventory.get("languages"):
        summary_bits.append(f"languages={','.join(inventory['languages'])}")
    if inventory.get("infra"):
        summary_bits.append(f"infra={','.join(inventory['infra'])}")
    if inventory.get("ci"):
        summary_bits.append(f"ci={','.join(inventory['ci'])}")
    summary = ", ".join(summary_bits)

    for pillar in PILLARS:
        path = _pillar_report_path(base, pillar)
        if not path.exists():
            continue
        content = _read_text(path)
        entries = _parse_questions_from_report(content)
        new_content = content
        for entry in entries:
            block = entry["block"]
            question_text = _normalize_text(entry.get("question") or entry.get("title") or "")
            current_status = entry.get("status") or "unanswered"
            answer_text = _parse_field(block, "Answer")
            if answer_text:
                current_status = "answered"
            elif current_status == "answered":
                current_status = "partial" if summary else "needs_human"
            ev_value = summary if summary else ""
            block_new = _replace_field(block, "Evidence", ev_value)
            if current_status == "answered":
                block_new = _replace_field(block_new, "Status", "answered")
            if current_status != "answered":
                if summary:
                    block_new = _replace_field(block_new, "Status", "partial")
                else:
                    block_new = _replace_field(block_new, "Status", "needs_human")
            if question_text and current_status != "answered":
                existing_hq = _parse_field(block_new, "Human Questions")
                if not existing_hq or existing_hq.startswith("Please describe how your team addresses:"):
                    block_new = _replace_field(
                        block_new,
                        "Human Questions",
                        f"Please describe how your team addresses: {question_text}",
                    )
            if question_text:
                block_new = _replace_field(block_new, "Question", question_text)
                title = _short_title(question_text)
                block_new = re.sub(
                    r"^##\s+[^:]+:.*$",
                    f"## {entry['id']}: {title}",
                    block_new,
                    flags=re.MULTILINE,
                )
            block_new = re.sub(r"^##\s+([^:]+):\s+", r"## \1: ", block_new, flags=re.MULTILINE)
            block_new = block_new.replace("\u00a0", " ").replace("Â", " ")
            new_content = new_content.replace(block, block_new)
        new_content = re.sub(r"^##\s+([^:]+):\s+", r"## \1: ", new_content, flags=re.MULTILINE)
        new_content = new_content.replace("\u00a0", " ").replace("Â", " ")
        _write_text(path, new_content)


def cmd_list_unanswered(args: argparse.Namespace) -> None:
    reports_dir = Path(args.reports_dir or REPORTS_DIR_DEFAULT)
    base, _ = _report_paths(reports_dir, args.assessment)
    output = []
    for pillar in PILLARS:
        path = _pillar_report_path(base, pillar)
        if not path.exists():
            continue
        content = _read_text(path)
        entries = _parse_questions_from_report(content)
        for entry in entries:
            if entry["status"] in {"", "unanswered", "needs_human", "partial"}:
                output.append({"pillar": pillar, "question_id": entry["id"], "status": entry["status"]})
    print(json.dumps(output, indent=2))


def cmd_record_answer(args: argparse.Namespace) -> None:
    reports_dir = Path(args.reports_dir or REPORTS_DIR_DEFAULT)
    base, _ = _report_paths(reports_dir, args.assessment)
    raw_answer = _read_text(Path(args.answer_file))
    answer_text = re.sub(r"\s+", " ", raw_answer).strip()
    updated = False

    for pillar in PILLARS:
        path = _pillar_report_path(base, pillar)
        if not path.exists():
            continue
        content = _read_text(path)
        entries = _parse_questions_from_report(content)
        new_content = content
        for entry in entries:
            if entry["id"] != args.question_id:
                continue
            block = entry["block"]
            block_new = _replace_field(block, "Status", args.status)
            block_new = _replace_field(block_new, "Confidence", args.confidence)
            block_new = re.sub(r"^Answer:.*$", f"Answer: {answer_text}", block_new, flags=re.MULTILINE)
            now = dt.datetime.now(dt.timezone.utc).isoformat()
            block_new = _replace_field(block_new, "Last Updated", now)
            new_content = new_content.replace(block, block_new)
            updated = True
        if new_content != content:
            _write_text(path, new_content)

    if not updated:
        raise WAIError("Question ID not found in reports")


def cmd_sync_kanbus(args: argparse.Namespace) -> None:
    reports_dir = Path(args.reports_dir or REPORTS_DIR_DEFAULT)
    base, _ = _report_paths(reports_dir, args.assessment)
    kanbus_map = json.loads(_read_text(base / "kanbus-map.json"))
    try:
        snapshot = json.loads(_run(["kanbus", "console", "snapshot"]))
        issues = snapshot.get("issues", [])
    except Exception:
        issues = []

    for pillar in PILLARS:
        path = _pillar_report_path(base, pillar)
        if not path.exists():
            continue
        content = _read_text(path)
        entries = _parse_questions_from_report(content)
        for entry in entries:
            qid = entry["id"]
            task_id = kanbus_map["tasks"].get(qid)
            if not task_id:
                continue
            task_id = _resolve_full_id(task_id, issues=issues)
            status = entry["status"]
            answer = _parse_field(entry["block"], "Answer")
            if answer:
                _kanbus_comment(task_id, f"Answer:\n{answer}")
            if status == "answered":
                _kanbus_update_status(task_id, "closed")
            elif status == "needs_human":
                _kanbus_update_status(task_id, "blocked")

    # Close epics if all tasks closed
    for pillar, epic_id in kanbus_map.get("epics", {}).items():
        epic_id = _resolve_full_id(epic_id, issues=issues)
        # naive: if every task is closed in report, close epic
        all_closed = True
        path = _pillar_report_path(base, pillar)
        if not path.exists():
            continue
        content = _read_text(path)
        entries = _parse_questions_from_report(content)
        for entry in entries:
            if entry["status"] != "answered":
                all_closed = False
                break
        if all_closed:
            _kanbus_update_status(epic_id, "closed")


def cmd_validate(args: argparse.Namespace) -> None:
    reports_dir = Path(args.reports_dir or REPORTS_DIR_DEFAULT)
    base, _ = _report_paths(reports_dir, args.assessment)
    errors = []
    for pillar in PILLARS:
        path = _pillar_report_path(base, pillar)
        if not path.exists():
            errors.append(f"missing pillar report: {pillar}")
            continue
        content = _read_text(path)
        entries = _parse_questions_from_report(content)
        ids = set()
        for entry in entries:
            if entry["id"] in ids:
                errors.append(f"duplicate question id {entry['id']} in {pillar}")
            ids.add(entry["id"])
            if entry["status"] and entry["status"] not in STATUS_VALUES:
                errors.append(f"invalid status {entry['status']} in {entry['id']}")
            if entry["confidence"] and entry["confidence"] not in CONFIDENCE_VALUES:
                errors.append(f"invalid confidence {entry['confidence']} in {entry['id']}")
    if errors:
        for err in errors:
            print(err)
        sys.exit(1)
    print("ok")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wai")
    sub = parser.add_subparsers(dest="command")

    p_fetch = sub.add_parser("fetch")
    p_fetch.add_argument("--refresh", action="store_true")
    p_fetch.add_argument("--cache-dir")

    p_init = sub.add_parser("init")
    p_init.add_argument("--target-dir", required=True)
    p_init.add_argument("--assessment")
    p_init.add_argument("--reports-dir")
    p_init.add_argument("--cache-dir")

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("--target-dir", required=True)
    p_scan.add_argument("--assessment", required=True)
    p_scan.add_argument("--reports-dir")
    p_scan.add_argument("--with", dest="with_scanners")

    p_apply = sub.add_parser("apply-evidence")
    p_apply.add_argument("--assessment", required=True)
    p_apply.add_argument("--reports-dir")

    p_list = sub.add_parser("list-unanswered")
    p_list.add_argument("--assessment", required=True)
    p_list.add_argument("--reports-dir")

    p_record = sub.add_parser("record-answer")
    p_record.add_argument("--assessment", required=True)
    p_record.add_argument("--question-id", required=True)
    p_record.add_argument("--status", required=True)
    p_record.add_argument("--confidence", default="n/a")
    p_record.add_argument("--answer-file", required=True)
    p_record.add_argument("--reports-dir")

    p_sync = sub.add_parser("sync-kanbus")
    p_sync.add_argument("--assessment", required=True)
    p_sync.add_argument("--reports-dir")

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("--assessment", required=True)
    p_validate.add_argument("--reports-dir")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "fetch":
            cmd_fetch(args)
        elif args.command == "init":
            cmd_init(args)
        elif args.command == "scan":
            cmd_scan(args)
        elif args.command == "apply-evidence":
            cmd_apply_evidence(args)
        elif args.command == "list-unanswered":
            cmd_list_unanswered(args)
        elif args.command == "record-answer":
            cmd_record_answer(args)
        elif args.command == "sync-kanbus":
            cmd_sync_kanbus(args)
        elif args.command == "validate":
            cmd_validate(args)
        else:
            parser.print_help()
            sys.exit(1)
    except WAIError as exc:
        print(f"error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    import shutil

    main()
