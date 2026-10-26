import json
from pathlib import Path

from app.pipeline import rules_engine as re_


def test_date_operators():
    facts = {"a": "2026-03-31", "b": "2026-04-15"}
    assert re_.check({"fact": "a", "op": "before", "ref": "b"}, facts)
    assert not re_.check({"fact": "b", "op": "before", "ref": "a"}, facts)
    assert re_.check({"fact": "b", "op": "within_days", "ref": "a", "days": 30}, facts)
    assert not re_.check({"fact": "b", "op": "within_days", "ref": "a", "days": 10}, facts)
    assert re_.check({"fact": "a", "op": "differs", "ref": "b"}, facts)


def test_missing_facts_never_match_comparisons():
    assert not re_.check({"fact": "x", "op": "lt", "value": 3}, {})
    assert re_.check({"fact": "x", "op": "missing"}, {})
    assert not re_.check({"fact": "x", "op": "not_empty"}, {"x": []})
    assert re_.check({"fact": "x", "op": "not_empty"}, {"x": ["one"]})


def test_numbers_text_and_similarity():
    facts = {"n": "1,200", "name": "Vidyaprakash College of Engineering", "inst": "VIDYAPRAKASH COLLEGE OF ENGINEERING",
             "other": "Gulmohar Institute"}
    assert re_.check({"fact": "n", "op": "gt", "value": 1000}, facts)
    assert re_.check({"fact": "name", "op": "eq", "ref": "inst"}, facts)
    assert not re_.check({"fact": "name", "op": "similar_lt", "ref": "inst", "value": 0.85}, facts)
    assert re_.check({"fact": "other", "op": "similar_lt", "ref": "inst", "value": 0.85}, facts)
    assert re_.check({"fact": "name", "op": "in", "value": ["vidyaprakash college of engineering"]}, facts)


def test_render_formats_dates_and_lists():
    assert re_.render("till {d} for {l}", {"d": "2026-03-31", "l": ["a", "b"]}) == "till 31-03-2026 for a; b"
    assert re_.render("{missing}", {}) == "—"


def test_validate_rulebook_reports_problems():
    bad = {"rules": [{"rule_id": "X", "title": "", "rows": [{"when": [{"fact": "f", "op": "nope"}], "severity": "huge",
                                                            "category": "OTHER", "title": ""}]},
                     {"rule_id": "X", "title": "dup", "rows": []}]}
    problems = re_.validate_rulebook(bad)
    text = " | ".join(problems)
    for expected in ("duplicate rule ID", "title is required", "unknown operator", "severity must be", "category must be"):
        assert expected in text


def test_default_rulebook_is_valid():
    content = json.loads((Path(__file__).resolve().parents[1] / "app/rulebook/default_rulebook.json").read_text())
    assert re_.validate_rulebook(content) == []


def test_each_document_scope_and_applies_to():
    content = {"rules": [
        {"rule_id": "Q", "title": "q", "scope": "each_document", "rows": [
            {"when": [{"fact": "this.verify_status", "op": "eq", "value": "MISMATCH"}], "severity": "high",
             "category": "VERIFICATION", "title": "{this.label} mismatch"}]},
        {"rule_id": "E", "title": "only EOA", "applies_to": {"app_types": ["EOA"]}, "rows": [
            {"when": [{"fact": "x", "op": "exists"}], "severity": "info", "category": "QUALITY", "title": "t"}]},
    ]}
    facts = {"application.type": "NEW_PROGRAMME", "x": 1}
    scopes = [{"this.document_id": "d1", "this.label": "Fire NOC", "this.verify_status": "MISMATCH"},
              {"this.document_id": "d2", "this.label": "Deed", "this.verify_status": "VERIFIED"}]
    matches = re_.evaluate(content, facts, scopes)
    assert [m.title for m in matches] == ["Fire NOC mismatch"]
    assert matches[0].scope_doc_id == "d1"
