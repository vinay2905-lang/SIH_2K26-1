"""Preliminary tampering and anomaly signals. These are indicators for a person to check, never proof."""
import io
import re
from datetime import datetime

import imagehash
import numpy as np
from PIL import Image, ImageChops

from .extract import Field
from .ingest import Ingested

EDITING_TOOLS = ("photoshop", "gimp", "ilovepdf", "pdf editor", "sejda", "smallpdf", "pdfescape", "canva",
                 "phantompdf", "nitro pdf", "pdf-xchange editor", "inkscape")


def _pdf_date(value: str | None) -> datetime | None:
    m = re.match(r"^D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?", value or "")
    if not m:
        return None
    parts = [int(p) if p else 0 for p in m.groups()]
    try:
        return datetime(parts[0], parts[1], parts[2], parts[3], parts[4], parts[5])
    except ValueError:
        return None


def pdf_signals(ing: Ingested, fields: list[Field], signature: dict | None) -> list[dict]:
    out: list[dict] = []
    for run in ing.hidden_text:
        visible = run.get("visible_text") or "nothing"
        out.append({
            "code": "TEXT_COVERED", "severity": "high", "page": run["page"], "bbox": run["bbox"],
            "title": "Text covered by a white box and replaced",
            "message": f"The file still contains “{run['hidden_text']}” under a white box; the visible text there is "
                       f"“{visible}”.",
        })
    meta = ing.meta or {}
    tool = " ".join(str(meta.get(k, "")) for k in ("producer", "creator")).lower()
    hit = next((t for t in EDITING_TOOLS if t in tool), None)
    if hit:
        out.append({"code": "EDITING_TOOL", "severity": "warning", "page": 0, "bbox": None,
                    "title": "Saved with a document-editing tool",
                    "message": f"File metadata names an editing tool ({meta.get('producer') or meta.get('creator')})."})
    created, modified = _pdf_date(meta.get("creationDate")), _pdf_date(meta.get("modDate"))
    if created and modified and (modified - created).days >= 2 and meta.get("eof_markers", 1) > 1 \
            and not (signature or {}).get("present"):
        out.append({"code": "EDITED_LATER", "severity": "warning", "page": 0, "bbox": None,
                    "title": "File changed after it was issued",
                    "message": f"Created {created:%d-%m-%Y}, saved again {modified:%d-%m-%Y} "
                               f"({(modified - created).days} days later)."})
    by_name = {f.name: f for f in fields}
    issued, valid_from, valid_till = by_name.get("issue_date"), by_name.get("valid_from"), by_name.get("valid_till")
    if issued and valid_till and issued.normalized and valid_till.normalized and issued.normalized > valid_till.normalized:
        out.append({"code": "DATE_ORDER", "severity": "warning", "page": valid_till.page, "bbox": valid_till.bbox,
                    "title": "Dates out of order", "message": f"Issued {issued.value}, but valid only till {valid_till.value}."})
    if valid_from and valid_till and valid_from.normalized and valid_till.normalized \
            and valid_from.normalized > valid_till.normalized:
        out.append({"code": "DATE_ORDER", "severity": "warning", "page": valid_till.page, "bbox": valid_till.bbox,
                    "title": "Dates out of order", "message": f"Valid from {valid_from.value} is after valid till {valid_till.value}."})
    if signature and signature.get("present"):
        if not signature.get("intact") or signature.get("modified_after_signing"):
            out.append({"code": "SIGNATURE_BROKEN", "severity": "high", "page": 0, "bbox": None,
                        "title": "Signed document was changed after signing",
                        "message": signature.get("summary", "The digital signature does not cover the current content.")})
        elif not signature.get("trusted"):
            out.append({"code": "SIGNATURE_UNTRUSTED", "severity": "warning", "page": 0, "bbox": None,
                        "title": "Signer not from a trusted authority", "message": signature.get("summary", "")})
    return out


def _gps_to_decimal(values, ref) -> float | None:
    try:
        d, m, s = (float(v) for v in values)
        dec = d + m / 60 + s / 3600
        return round(-dec if ref in ("S", "W") else dec, 6)
    except Exception:
        return None


def ela_score(img: Image.Image, data: bytes) -> float | None:
    """Error level analysis for JPEGs: share of 16px blocks whose recompression error stands out."""
    if not data[:3] == b"\xff\xd8\xff":
        return None
    rgb = img.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=90)
    diff = np.asarray(ImageChops.difference(rgb, Image.open(io.BytesIO(buf.getvalue()))).convert("L"), dtype=np.float32)
    h, w = (diff.shape[0] // 16) * 16, (diff.shape[1] // 16) * 16
    if h == 0 or w == 0:
        return None
    blocks = diff[:h, :w].reshape(h // 16, 16, w // 16, 16).mean(axis=(1, 3))
    median = float(np.median(blocks)) + 0.5
    outliers = (blocks > max(6.0, median * 6)).mean()
    return round(float(outliers), 4)


def photo_info(img: Image.Image, data: bytes) -> tuple[dict, list[dict]]:
    info: dict = {"phash": str(imagehash.phash(img.convert("RGB")))}
    exif = None
    try:
        exif = Image.open(io.BytesIO(data)).getexif()
    except Exception:
        pass
    signals: list[dict] = []
    if exif:
        software = str(exif.get(305, "") or "")
        info["software"] = software or None
        sub = exif.get_ifd(0x8769)
        taken = sub.get(36867) or exif.get(306)
        if taken:
            try:
                info["taken_at"] = datetime.strptime(str(taken), "%Y:%m:%d %H:%M:%S").isoformat()
            except ValueError:
                pass
        gps = exif.get_ifd(0x8825)
        if gps and 2 in gps and 4 in gps:
            info["gps_lat"] = _gps_to_decimal(gps[2], gps.get(1, "N"))
            info["gps_lon"] = _gps_to_decimal(gps[4], gps.get(3, "E"))
        if software and any(t in software.lower() for t in EDITING_TOOLS):
            signals.append({"code": "PHOTO_EDITED", "severity": "warning", "page": 0, "bbox": None,
                            "title": "Photo saved by an editing tool", "message": f"Photo metadata names {software}."})
    score = ela_score(img, data)
    info["ela"] = score
    if score is not None and 0.004 < score < 0.35:
        signals.append({"code": "ELA_REGION", "severity": "warning", "page": 0, "bbox": None,
                        "title": "Part of the photo compresses differently",
                        "message": f"{score:.1%} of the photo shows a different compression level, which can mean a "
                                   "pasted region. Check visually."})
    return info, signals
