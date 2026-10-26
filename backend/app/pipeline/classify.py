"""Identify the document type from its text (keyword evidence, explainable)."""
import re

from .ingest import Ingested
from .templates import TEMPLATES


def classify(ing: Ingested) -> tuple[str | None, float, list[str]]:
    """Return (doc_type, confidence 0-1, matched keywords)."""
    text = re.sub(r"\s+", " ", ing.text.lower())
    if ing.kind == "image" and len(ing.words) < 15:
        return "LAB_PHOTO", 0.9, ["photograph with little or no text"]
    scores: dict[str, tuple[float, list[str]]] = {}
    for doc_type, tpl in TEMPLATES.items():
        total, hits = 0.0, []
        for kw, weight in tpl.get("keywords", {}).items():
            n = len(re.findall(r"\b" + re.escape(kw) + r"\b", text))
            if n:
                total += weight * min(n, 2)
                hits.append(kw)
        scores[doc_type] = (total, hits)
    ranked = sorted(scores.items(), key=lambda kv: kv[1][0], reverse=True)
    (best, (top, hits)), (_, (second, _)) = ranked[0], ranked[1]
    if top == 0:
        return None, 0.0, []
    confidence = top / (top + second + 1.5)
    return best, round(min(confidence, 0.99), 2), hits
