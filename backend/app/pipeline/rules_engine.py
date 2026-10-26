"""Evaluate a versioned rulebook (decision tables written as data, not code) against application facts.

A rule has rows; a row matches when all its conditions hold. Every match becomes a finding that names the
rule, the row, the handbook source and the evidence it relied on. No `eval` is used: conditions are
structured {fact, op, value|ref} objects, so non-programmers can edit them safely through the UI.
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from rapidfuzz import fuzz

OPS = {
    "exists": "is present", "missing": "is missing", "eq": "equals", "ne": "does not equal",
    "lt": "is less than", "le": "is at most", "gt": "is more than", "ge": "is at least",
    "before": "is before", "after": "is after", "within_days": "falls within N days after",
    "in": "is one of", "not_in": "is not one of", "not_empty": "has entries", "empty": "has no entries",
    "similar_lt": "is less similar than", "differs": "differs from",
}
SEVERITIES = ("critical", "high", "warning", "info")
CATEGORIES = ("MISSING_DOCUMENT", "EXPIRED_DOCUMENT", "INCONSISTENCY", "ANOMALY", "VERIFICATION",
              "COMPLIANCE_GAP", "QUALITY")


class RuleError(ValueError):
    pass


@dataclass
class Match:
    rule_id: str
    row: int
    severity: str
    category: str
    title: str
    message: str
    source: str
    doc_type: str | None
    evidence_keys: list[str]
    scope_doc_id: str | None = None
    facts_used: dict = field(default_factory=dict)


def _as_date(v) -> date | None:
    if isinstance(v, date):
        return v
    if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", v):
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    return None


def _as_num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", ""))
        except ValueError:
            return None
    return None


def _norm_text(v) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(v).lower()).strip()


def _cmp(a, b):
    da, db = _as_date(a), _as_date(b)
    if da and db:
        return (da > db) - (da < db)
    na, nb = _as_num(a), _as_num(b)
    if na is not None and nb is not None:
        return (na > nb) - (na < nb)
    return None


def check(cond: dict, facts: dict) -> bool:
    op = cond.get("op")
    if op not in OPS:
        raise RuleError(f"unknown operator {op!r}")
    v = facts.get(cond.get("fact"))
    other = facts.get(cond["ref"]) if "ref" in cond else cond.get("value")
    if op == "exists":
        return v not in (None, "", [], False)
    if op == "missing":
        return v in (None, "", [], False)
    if op == "not_empty":
        return isinstance(v, (list, tuple)) and len(v) > 0
    if op == "empty":
        return not v
    if v is None or (other is None and op not in ("in", "not_in")):
        return False
    if op in ("eq", "ne"):
        c = _cmp(v, other)
        same = (c == 0) if c is not None else _norm_text(v) == _norm_text(other)
        return same if op == "eq" else not same
    if op == "differs":
        c = _cmp(v, other)
        return (c != 0) if c is not None else _norm_text(v) != _norm_text(other)
    if op in ("lt", "le", "gt", "ge"):
        c = _cmp(v, other)
        if c is None:
            return False
        return {"lt": c < 0, "le": c <= 0, "gt": c > 0, "ge": c >= 0}[op]
    if op in ("before", "after", "within_days"):
        dv, do = _as_date(v), _as_date(other)
        if not dv or not do:
            return False
        days = int(cond.get("days", 0))
        if op == "before":
            return dv < do + timedelta(days=days)
        if op == "after":
            return dv > do + timedelta(days=days)
        return do <= dv < do + timedelta(days=days)
    if op in ("in", "not_in"):
        values = [_norm_text(x) for x in (cond.get("value") or [])]
        inside = _norm_text(v) in values
        return inside if op == "in" else not inside
    if op == "similar_lt":
        threshold = float(cond.get("value", 0.85))
        ref = facts.get(cond.get("ref"))
        if ref is None:
            return False
        return fuzz.token_set_ratio(_norm_text(v), _norm_text(ref)) / 100.0 < threshold
    return False


def display(v) -> str:
    d = _as_date(v)
    if d:
        return d.strftime("%d-%m-%Y")
    if isinstance(v, float):
        return f"{v:.2f}" if abs(v) < 1 else f"{v:.1f}".rstrip("0").rstrip(".")
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v)
    return str(v)


def render(template: str, facts: dict) -> str:
    def sub(m):
        key = m.group(1)
        return display(facts[key]) if facts.get(key) is not None else "—"

    return re.sub(r"\{([a-zA-Z0-9_.:\- ]+)\}", sub, template)


def validate_rulebook(content: dict) -> list[str]:
    """Return a list of human-readable problems (empty when the rulebook is usable)."""
    problems = []
    seen = set()
    if not isinstance(content.get("rules"), list):
        return ["rulebook has no rules list"]
    for r in content["rules"]:
        rid = r.get("rule_id") or "?"
        if len(rid) > 40 or not re.match(r"^[A-Z0-9][A-Z0-9_\-]*$", rid):
            problems.append(f"{rid[:40]}: rule ID must be up to 40 capital letters, digits or dashes")
        if len(r.get("title", "")) > 200:
            problems.append(f"{rid}: title is longer than 200 characters")
        if rid in seen:
            problems.append(f"{rid}: duplicate rule ID")
        seen.add(rid)
        if not r.get("title"):
            problems.append(f"{rid}: title is required")
        if r.get("scope", "application") not in ("application", "each_document"):
            problems.append(f"{rid}: scope must be application or each_document")
        for i, row in enumerate(r.get("rows", []), start=1):
            if row.get("severity") not in SEVERITIES:
                problems.append(f"{rid} row {i}: severity must be one of {', '.join(SEVERITIES)}")
            if row.get("category") not in CATEGORIES:
                problems.append(f"{rid} row {i}: category must be one of {', '.join(CATEGORIES)}")
            if not row.get("when"):
                problems.append(f"{rid} row {i}: needs at least one condition")
            for c in row.get("when", []):
                if c.get("op") not in OPS:
                    problems.append(f"{rid} row {i}: unknown operator {c.get('op')!r}")
                if not c.get("fact"):
                    problems.append(f"{rid} row {i}: a condition has no fact")
            if not row.get("title"):
                problems.append(f"{rid} row {i}: finding title is required")
    for app_type, items in (content.get("checklists") or {}).items():
        for it in items:
            if not it.get("doc_type"):
                problems.append(f"checklist {app_type}: item without doc_type")
    return problems


def _applies(rule: dict, facts: dict) -> bool:
    if not rule.get("enabled", True):
        return False
    a = rule.get("applies_to") or {}
    types, states = a.get("app_types") or [], a.get("states") or []
    if types and facts.get("application.type") not in types:
        return False
    if states and facts.get("institution.state_code") not in states:
        return False
    return True


def evaluate(content: dict, facts: dict, doc_scopes: list[dict]) -> list[Match]:
    """doc_scopes: one fact dict per processed document (keys prefixed `this.`)."""
    matches: list[Match] = []
    for rule in content.get("rules", []):
        if not _applies(rule, facts):
            continue
        scopes = [dict(facts, **s) for s in doc_scopes] if rule.get("scope") == "each_document" else [facts]
        for scope in scopes:
            for i, row in enumerate(rule.get("rows", []), start=1):
                if all(check(c, scope) for c in row.get("when", [])):
                    doc_type = row.get("doc_type") or scope.get("this.doc_type")
                    keys = list(row.get("evidence") or [])
                    if not keys:
                        keys = [c["fact"] for c in row["when"]] + [c["ref"] for c in row["when"] if "ref" in c]
                    matches.append(Match(
                        rule_id=rule["rule_id"], row=i, severity=row["severity"], category=row["category"],
                        title=render(row["title"], scope), message=render(row.get("message", row["title"]), scope),
                        source=rule.get("source", ""), doc_type=doc_type, evidence_keys=keys,
                        scope_doc_id=scope.get("this.document_id"),
                        facts_used={k: scope.get(k) for k in keys},
                    ))
    return matches
