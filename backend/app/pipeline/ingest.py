"""Read a PDF or image into positioned words and visual lines (text layer first, Tesseract OCR as fallback)."""
import io
import logging
from collections import Counter
from dataclasses import dataclass, field

import fitz  # PyMuPDF
from PIL import Image, ImageOps

from ..config import get_settings

log = logging.getLogger("pramaan.ingest")
OCR_DPI = 300
MIN_TEXT_WORDS = 8


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page: int
    conf: float = 0.99


@dataclass
class Line:
    page: int
    words: list[Word]
    text: str = ""
    spans: list[tuple[int, int]] = field(default_factory=list)

    def build(self) -> "Line":
        self.words.sort(key=lambda w: w.x0)
        parts, pos = [], 0
        for w in self.words:
            parts.append(w.text)
            self.spans.append((pos, pos + len(w.text)))
            pos += len(w.text) + 1
        self.text = " ".join(parts)
        return self


@dataclass
class Ingested:
    kind: str  # pdf | image
    pages: list[dict]
    words: list[Word]
    lines: list[Line]
    text_source: str  # TEXT_LAYER | OCR | MIXED | NONE
    ocr_confidence: float | None
    meta: dict
    hidden_text: list[dict]
    image: Image.Image | None = None

    @property
    def text(self) -> str:
        return "\n".join(l.text for l in self.lines)


def sniff_kind(data: bytes) -> str | None:
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff":
        return "image"
    return None


_tesseract_ok: bool | None = None


def ocr_available() -> bool:
    global _tesseract_ok
    if _tesseract_ok is None:
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            _tesseract_ok = True
        except Exception:
            _tesseract_ok = False
            log.warning("Tesseract not found: scanned documents will be routed to manual review")
    return _tesseract_ok


def ocr_image(img: Image.Image, page: int, scale: float) -> list[Word]:
    import pytesseract

    data = pytesseract.image_to_data(img.convert("L"), lang=get_settings().ocr_languages,
                                     output_type=pytesseract.Output.DICT)
    words = []
    for i, txt in enumerate(data["text"]):
        txt = (txt or "").strip()
        conf = float(data["conf"][i])
        if not txt or conf < 0:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(Word(txt, x * scale, y * scale, (x + w) * scale, (y + h) * scale, page, conf / 100.0))
    return words


def group_lines(words: list[Word]) -> list[Line]:
    lines: list[Line] = []
    for page in sorted({w.page for w in words}):
        current: list[Word] = []
        ref_y = None
        for w in sorted((w for w in words if w.page == page), key=lambda w: ((w.y0 + w.y1) / 2, w.x0)):
            yc, h = (w.y0 + w.y1) / 2, max(w.y1 - w.y0, 1)
            if ref_y is not None and abs(yc - ref_y) > max(2.5, 0.45 * h):
                lines.append(Line(page, current).build())
                current = []
            if not current:
                ref_y = yc
            current.append(w)
        if current:
            lines.append(Line(page, current).build())
    return lines


def _white(fill) -> bool:
    return fill is not None and len(fill) >= 3 and min(fill[:3]) > 0.94


def _overlap(a, b) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    area = max((a[2] - a[0]) * (a[3] - a[1]), 1e-6)
    return (x1 - x0) * (y1 - y0) / area


def find_hidden_words(page: fitz.Page, words: list[Word]) -> tuple[list[Word], list[dict]]:
    """Text painted over by a later white box is hidden from a reader but still sits in the file.

    Returns the words a reader actually sees, plus each hidden run for the forensic report.
    """
    try:
        drawings = [d for d in page.get_drawings() if _white(d.get("fill"))]
        spans = page.get_texttrace()
    except Exception:
        return words, []
    page_area = page.rect.width * page.rect.height
    runs, boxes = [], []
    for d in drawings:
        r = d["rect"]
        if r.width * r.height > 0.25 * page_area or r.width < 4 or r.height < 4:
            continue
        rb = (r.x0, r.y0, r.x1, r.y1)
        seq = d.get("seqno", 0)
        under = [s for s in spans if s.get("seqno", 0) < seq and _overlap(s["bbox"], rb) > 0.6]
        over = [s for s in spans if s.get("seqno", 0) > seq and _overlap(s["bbox"], rb) > 0.3]
        hidden_text = " ".join("".join(chr(c[0]) for c in s["chars"]) for s in under).strip()
        if not hidden_text:
            continue
        visible_text = " ".join("".join(chr(c[0]) for c in s["chars"]) for s in over).strip()
        boxes.append((rb, Counter(visible_text.split())))
        runs.append({"page": page.number, "bbox": [round(v, 1) for v in rb],
                     "hidden_text": hidden_text, "visible_text": visible_text})
    if not boxes:
        return words, []
    visible = []
    for w in words:
        box = next(((rb, allowed) for rb, allowed in boxes if _overlap((w.x0, w.y0, w.x1, w.y1), rb) > 0.6), None)
        if box is None:
            visible.append(w)
            continue
        allowed = box[1]
        if allowed[w.text] > 0:
            allowed[w.text] -= 1
            visible.append(w)
    return visible, runs


def ingest(data: bytes) -> Ingested:
    kind = sniff_kind(data)
    if kind == "pdf":
        return _ingest_pdf(data)
    if kind == "image":
        return _ingest_image(data)
    raise ValueError("Unsupported file: only PDF, PNG and JPEG are accepted")


def _ingest_pdf(data: bytes) -> Ingested:
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if doc.needs_pass:
            raise ValueError("Password-protected PDFs cannot be checked")
        pages, words, hidden = [], [], []
        ocr_pages, confs = 0, []
        for page in doc:
            pages.append({"w": round(page.rect.width, 2), "h": round(page.rect.height, 2), "unit": "pt"})
            pw = [Word(t[4], t[0], t[1], t[2], t[3], page.number) for t in page.get_text("words") if t[4].strip()]
            if len(pw) >= MIN_TEXT_WORDS:
                pw, runs = find_hidden_words(page, pw)
                hidden.extend(runs)
            elif ocr_available():
                pix = page.get_pixmap(dpi=OCR_DPI)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                pw = ocr_image(img, page.number, 72.0 / OCR_DPI)
                ocr_pages += 1
                confs.extend(w.conf for w in pw if len(w.text) > 1)
            words.extend(pw)
        meta = {k: v for k, v in (doc.metadata or {}).items() if v}
        meta["eof_markers"] = data.count(b"%%EOF")
        meta["page_count"] = doc.page_count
    finally:
        doc.close()
    if ocr_pages == 0:
        source = "TEXT_LAYER" if words else "NONE"
    else:
        source = "OCR" if ocr_pages == len(pages) else "MIXED"
    ocr_conf = round(sum(confs) / len(confs), 3) if confs else None
    return Ingested("pdf", pages, words, group_lines(words), source, ocr_conf, meta, hidden)


def _ingest_image(data: bytes) -> Ingested:
    img = Image.open(io.BytesIO(data))
    img.load()
    exif = img.getexif()
    img = ImageOps.exif_transpose(img)
    pages = [{"w": img.width, "h": img.height, "unit": "px"}]
    words, confs = [], []
    if ocr_available():
        words = [w for w in ocr_image(img, 0, 1.0) if w.conf >= 0.4]
        confs = [w.conf for w in words if len(w.text) > 1]
    meta = {"format": img.format or "image", "mode": img.mode, "width": img.width, "height": img.height,
            "exif": {int(k): str(v)[:120] for k, v in exif.items()} if exif else {}}
    ocr_conf = round(sum(confs) / len(confs), 3) if confs else None
    return Ingested("image", pages, words, group_lines(words), "OCR" if words else "NONE", ocr_conf, meta, [],
                    image=img)


def render_page(data: bytes, page_index: int, dpi: int = 110) -> bytes:
    kind = sniff_kind(data)
    if kind == "pdf":
        doc = fitz.open(stream=data, filetype="pdf")
        try:
            if page_index < 0 or page_index >= doc.page_count:
                raise IndexError("page out of range")
            return doc[page_index].get_pixmap(dpi=dpi).tobytes("png")
        finally:
            doc.close()
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if page_index != 0:
        raise IndexError("page out of range")
    if img.width > 1600:
        img = img.resize((1600, round(img.height * 1600 / img.width)))
    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG")
    return out.getvalue()
