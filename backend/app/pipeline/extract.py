"""Pull named fields out of document lines, keeping where each value sits on the page."""
import re
from dataclasses import dataclass
from datetime import date

from .ingest import Ingested, Line
from .templates import DATE_FIELDS, NUMBER_FIELDS, TEMPLATES, field_patterns


@dataclass
class Field:
    name: str
    value: str
    normalized: str | None
    page: int
    bbox: list[float] | None
    confidence: float


def parse_date(s: str) -> date | None:
    m = re.match(r"^\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\s*$", s or "")
    if not m:
        m2 = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$", s or "")
        if not m2:
            return None
        y, mo, d = map(int, m2.groups())
    else:
        d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def normalize(name: str, value: str) -> str | None:
    value = value.strip()
    if name in DATE_FIELDS:
        d = parse_date(value)
        return d.isoformat() if d else None
    if name in NUMBER_FIELDS:
        digits = re.sub(r"[^\d.]", "", value)
        return digits or None
    return re.sub(r"\s+", " ", value)


def _locate(line: Line, start: int, end: int) -> tuple[list[float] | None, float]:
    hit = [w for w, (a, b) in zip(line.words, line.spans) if a < end and b > start]
    if not hit:
        return None, 0.0
    bbox = [round(min(w.x0 for w in hit), 1), round(min(w.y0 for w in hit), 1),
            round(max(w.x1 for w in hit), 1), round(max(w.y1 for w in hit), 1)]
    return bbox, round(sum(w.conf for w in hit) / len(hit), 3)


def extract(ing: Ingested, doc_type: str | None, state_code: str | None) -> list[Field]:
    if not doc_type:
        return []
    out: list[Field] = []
    for name, patterns in field_patterns(doc_type, state_code).items():
        found = None
        for pattern in patterns:
            rx = re.compile(pattern, re.IGNORECASE)
            for line in ing.lines:
                m = rx.search(line.text)
                if m:
                    found = (line, m)
                    break
            if found:
                break
        if found:
            line, m = found
            raw = m.group("v").strip().rstrip(".,;")
            bbox, conf = _locate(line, m.start("v"), m.start("v") + len(raw))
            out.append(Field(name, raw, normalize(name, raw), line.page, bbox, conf))

    tpl = TEMPLATES.get(doc_type, {})
    if "intake_lines" in tpl:
        rx = re.compile(tpl["intake_lines"])
        for line in ing.lines:
            m = rx.search(line.text.strip())
            if m:
                prog = re.sub(r"\s+", " ", m.group("prog")).strip()
                bbox, conf = _locate(line, m.start("v"), m.end("v"))
                out.append(Field(f"intake::{prog}", m.group("v"), m.group("v"), line.page, bbox, conf))
    if "faculty_ids" in tpl:
        rx = re.compile(tpl["faculty_ids"])
        for line in ing.lines:
            for m in rx.finditer(line.text):
                bbox, conf = _locate(line, m.start("v"), m.end("v"))
                out.append(Field("faculty_id", m.group("v"), m.group("v"), line.page, bbox, conf))
    return out
