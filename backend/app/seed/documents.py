"""Synthetic document generator. Every file is marked SYNTHETIC SAMPLE and issued by a sandbox authority."""
import io
import random
import tempfile
from datetime import date, datetime
from pathlib import Path

import fitz
import piexif
import qrcode
from PIL import Image, ImageDraw, ImageFilter

A4 = (595, 842)
INK = (0.11, 0.13, 0.2)
MUTED = (0.35, 0.38, 0.44)
FOOT = "SYNTHETIC SAMPLE · generated for the PRAMAAN prototype · not a real certificate"


def d(s: str) -> str:
    """ISO date -> dd-mm-yyyy as printed on Indian certificates."""
    return date.fromisoformat(s).strftime("%d-%m-%Y")


def _qr_png(payload: str) -> bytes:
    img = qrcode.make(payload, box_size=6, border=1)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class Sheet:
    def __init__(self, producer: str = "PRAMAAN sandbox issuer", created: datetime | None = None):
        self.doc = fitz.open()
        self.page = self.doc.new_page(width=A4[0], height=A4[1])
        self.y = 60
        self.producer = producer
        self.created = created or datetime(2025, 3, 28, 10, 15)

    def seal(self, label: str):
        p = self.page
        c = fitz.Point(92, 92)
        p.draw_circle(c, 34, color=(0.48, 0.17, 0.17), width=1.2)
        p.draw_circle(c, 22, color=(0.48, 0.17, 0.17), width=0.7)
        p.insert_textbox(fitz.Rect(70, 84, 114, 104), label, fontsize=6.5, fontname="hebo", color=(0.48, 0.17, 0.17), align=1)

    def header(self, lines: list[str], seal_label: str = "SEAL"):
        self.seal(seal_label)
        y = 70
        for i, line in enumerate(lines):
            self.page.insert_text((140, y), line, fontsize=12 if i == 0 else 9.5, fontname="hebo" if i == 0 else "helv",
                                  color=INK if i < 2 else MUTED)
            y += 16 if i == 0 else 13
        self.page.draw_line((50, 138), (545, 138), color=INK, width=1.2)
        self.y = 162

    def pair(self, left: str, right: str | None = None):
        self.page.insert_text((60, self.y), left, fontsize=10, fontname="hebo", color=INK)
        if right:
            self.page.insert_text((400, self.y), right, fontsize=10, fontname="hebo", color=INK)
        self.y += 24

    def title(self, text: str):
        w = fitz.get_text_length(text, fontname="hebo", fontsize=13)
        self.page.insert_text(((A4[0] - w) / 2, self.y), text, fontsize=13, fontname="hebo", color=INK)
        self.y += 24

    def para(self, text: str, size: float = 10):
        rect = fitz.Rect(60, self.y - 10, 535, self.y + 70)
        rc = self.page.insert_textbox(rect, text, fontsize=size, fontname="helv", color=INK, align=3)
        used = 80 - rc if rc > 0 else 60
        self.y += used + 8

    def row(self, label: str, value: str):
        self.page.draw_rect(fitz.Rect(56, self.y - 13, 539, self.y + 7), color=(0.8, 0.82, 0.86), width=0.6)
        self.page.insert_text((62, self.y), label, fontsize=10, fontname="helv", color=MUTED)
        self.page.insert_text((230, self.y), value, fontsize=10, fontname="hebo", color=INK)
        self.y += 20

    def line(self, text: str, size: float = 10, bold: bool = False, x: float = 60):
        self.page.insert_text((x, self.y), text, fontsize=size, fontname="hebo" if bold else "helv", color=INK)
        self.y += size + 7

    def gap(self, n: float = 10):
        self.y += n

    def footer(self, signer: str, qr_payload: str | None = None):
        p = self.page
        if qr_payload:
            p.insert_image(fitz.Rect(60, 690, 140, 770), stream=_qr_png(qr_payload))
            p.insert_text((62, 782), "Scan to verify", fontsize=7, fontname="helv", color=MUTED)
        path = [(400, 720), (410, 706), (418, 724), (428, 704), (437, 722), (448, 708), (458, 720), (470, 710), (482, 716)]
        for a, b in zip(path, path[1:]):
            p.draw_line(a, b, color=(0.11, 0.18, 0.33), width=1.1)
        w = fitz.get_text_length(signer, fontname="hebo", fontsize=9)
        p.insert_text((442 - w / 2, 742), signer, fontsize=9, fontname="hebo", color=INK)
        p.insert_text((60, 818), FOOT, fontsize=7, fontname="helv", color=MUTED)

    def bytes(self, mod: datetime | None = None) -> bytes:
        fmt = lambda t: t.strftime("D:%Y%m%d%H%M%S+05'30'")
        self.doc.set_metadata({"producer": self.producer, "creator": self.producer, "title": "Synthetic sample",
                               "creationDate": fmt(self.created), "modDate": fmt(mod or self.created)})
        out = self.doc.tobytes(garbage=3, deflate=True)
        self.doc.close()
        return out


# --------------------------------------------------------------- doc types --
def fire_noc(c: dict) -> bytes:
    s = Sheet(created=datetime.fromisoformat(c["issue_date"] + "T10:15:00"))
    s.header(["OFFICE OF THE CHIEF FIRE OFFICER", f"{c['state']} Fire & Emergency Services · Sandbox Authority",
              "Fire Prevention Wing"], "FIRE\nSAFETY")
    s.pair(f"No. {c['cert_no']}", f"Date: {d(c['issue_date'])}")
    s.title("FIRE NO OBJECTION CERTIFICATE (FINAL)")
    s.para("This is to certify that the premises described below were inspected and found to comply with the fire "
           "prevention and life safety requirements applicable to the occupancy stated, subject to the conditions below.")
    s.row("Name of premises", c["premises_name"])
    s.row("Address", c["address"])
    s.row("Occupancy", "Educational (Group B)")
    s.row("Built-up area", f"{c['built_up_area']:,} m2")
    s.row("Fire safety systems", "Hydrants, sprinklers, detection and alarm")
    s.row("Valid from", d(c["valid_from"]))
    s.row(c.get("valid_label", "Valid till"), d(c["valid_till"]))
    s.gap(8)
    s.para("This certificate must be renewed before expiry. Any change of use, structure or occupancy load requires a "
           "fresh inspection.", 9)
    s.footer("Chief Fire Officer", f"PRAMAAN-SANDBOX|FIRE_NOC|{c['cert_no']}")
    return s.bytes()


def tamper_cover_text(pdf: bytes, old: str, new: str, producer: str = "iLovePDF", mod: datetime | None = None) -> bytes:
    """Simulate a forged date: paint a white box over the original text, write a new value on top, and save the
    change as an incremental update, the way common PDF editors do."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "t.pdf"
        path.write_bytes(pdf)
        doc = fitz.open(path)
        page = doc[0]
        for r in page.search_for(old):
            page.draw_rect(fitz.Rect(r.x0 - 1, r.y0 - 1, r.x1 + 1, r.y1 + 1), color=(1, 1, 1), fill=(1, 1, 1))
            page.insert_text((r.x0, r.y1 - 2.2), new, fontsize=10, fontname="hebo", color=INK)
        meta = doc.metadata
        meta["producer"] = producer
        meta["modDate"] = (mod or datetime(2026, 4, 9, 18, 2)).strftime("D:%Y%m%d%H%M%S+05'30'")
        doc.set_metadata(meta)
        doc.saveIncr()
        doc.close()
        return path.read_bytes()


def building_completion(c: dict) -> bytes:
    s = Sheet(created=datetime.fromisoformat(c["issue_date"] + "T11:00:00"))
    s.header([f"{c['city'].upper()} MUNICIPAL CORPORATION · SANDBOX", "Building Permission Department",
              "Town Planning Section"], "MUNICIPAL")
    s.pair(f"Certificate No. {c['cert_no']}", f"Date of issue: {d(c['issue_date'])}")
    s.title("BUILDING COMPLETION AND OCCUPANCY CERTIFICATE")
    s.para("Certified that the building described below has been completed as per the sanctioned plan and is fit for "
           "the occupancy stated. This completion certificate is issued under the building permission rules.")
    s.row("Name of premises", c["premises_name"])
    s.row("Address", c["address"])
    s.row("Built-up area", f"{c['built_up_area']:,} m2")
    s.row("Floors", c.get("floors", "Ground + 4"))
    s.row("Occupancy", "Educational institution")
    s.footer("Executive Engineer (Buildings)")
    return s.bytes()


def structural(c: dict) -> bytes:
    s = Sheet(created=datetime.fromisoformat(c["issue_date"] + "T12:00:00"))
    s.header(["STRUCTURAL STABILITY CERTIFICATE", "Chartered Structural Engineer · Sandbox panel",
              f"Licence No. SE/{c['state_code']}/2211"], "SE")
    s.pair(f"Certificate No. {c['cert_no']}", f"Date of issue: {d(c['issue_date'])}")
    s.para("I have inspected the buildings listed below and certify their structural stability for the declared use, "
           "including load bearing members, foundations and roof slabs.")
    s.row("Name of premises", c["premises_name"])
    s.row("Blocks inspected", "A, B and C")
    s.row("Valid till", d(c["valid_till"]))
    s.footer("Structural Engineer")
    return s.bytes()


def land_deed(c: dict) -> bytes:
    s = Sheet(created=datetime.fromisoformat(c["registration_date"] + "T15:00:00"))
    s.header(["SALE DEED (CONVEYANCE)", f"Office of the Sub-Registrar, {c['city']} · Sandbox",
              "Registration copy"], "SUB\nREG")
    s.pair(f"Registration No. {c['registration_no']}", f"Date of registration: {d(c['registration_date'])}")
    s.para("This sale deed records the conveyance of the land described below by the vendor to the purchaser, for "
           "the purpose of establishing an educational institution.")
    s.row("Purchaser", c["owner_name"])
    s.row("Survey No.", c["survey_no"])
    s.row("Area", f"{c['area_acres']} acres")
    s.row("Village / City", c["city"])
    s.footer("Sub-Registrar", f"PRAMAAN-SANDBOX|LAND_DEED|{c['registration_no']}")
    return s.bytes()


def affiliation(c: dict) -> bytes:
    s = Sheet(created=datetime.fromisoformat(c["issue_date"] + "T10:30:00"))
    s.header([c["university"].upper(), "Office of the Registrar · Sandbox", "Affiliation Section"], "UNIV")
    s.pair(f"Letter No. {c['letter_no']}", f"Date: {d(c['issue_date'])}")
    s.line(f"Subject: Grant of affiliation for the academic year {c['academic_year']}", bold=True)
    s.line(f"Institution: {c['institution_name']}")
    s.gap(4)
    s.para("The University is pleased to grant affiliation to the programmes listed below with the approved intake "
           "shown against each, subject to the conditions of affiliation.")
    s.line("Programme and approved intake", bold=True)
    for p in c["programmes"]:
        s.page.insert_text((60, s.y), p["programme"], fontsize=10, fontname="helv", color=INK)
        s.page.insert_text((470, s.y), str(p["approved_intake"]), fontsize=10, fontname="hebo", color=INK)
        s.y += 18
    s.footer("Registrar", f"PRAMAAN-SANDBOX|AFFILIATION_LETTER|{c['letter_no']}")
    return s.bytes()


def nba(c: dict) -> bytes:
    s = Sheet(created=datetime.fromisoformat(c["issue_date"] + "T10:00:00"))
    s.header(["NATIONAL BOARD OF ACCREDITATION · SANDBOX SPECIMEN", "Accreditation certificate (synthetic)",
              "For prototype testing only"], "NBA\nTEST")
    s.pair(f"Accreditation No. {c['accreditation_no']}")
    s.line(f"Institution: {c['institution_name']}")
    s.para("The programmes listed below are accredited for the period shown, subject to the accreditation norms.")
    for p in c["programmes"]:
        s.line(f"• {p}")
    s.row("Valid till", d(c["valid_till"]))
    s.footer("Member Secretary", f"PRAMAAN-SANDBOX|NBA_ACCREDITATION|{c['accreditation_no']}")
    return s.bytes()


def ter_receipt(c: dict) -> bytes:
    s = Sheet(created=datetime.fromisoformat(c["payment_date"] + "T09:40:00"))
    s.header(["PAYMENT RECEIPT · SANDBOX GATEWAY", "Approval process fee (TER)", "Online payment acknowledgement"], "PAID")
    s.row("Transaction ID", c["txn_id"])
    s.row("Paid by", c["institution_name"])
    s.row("Amount", f"Rs. {c['amount_text']}")
    s.row("Payment date", d(c["payment_date"]))
    s.row("Purpose", "Processing fee, approval cycle 2026-27")
    s.footer("System generated", f"PRAMAAN-SANDBOX|TER_RECEIPT|{c['txn_id']}")
    return s.bytes()


def affidavit(c: dict) -> bytes:
    s = Sheet(created=datetime.fromisoformat(c["date"] + "T11:30:00"))
    s.header(["AFFIDAVIT CUM UNDERTAKING", "On non-judicial stamp paper (synthetic)", "Before the Notary Public"], "NOTARY")
    s.para(f"I, {c['deponent']}, Principal of {c['institution_name']}, do hereby solemnly affirm and state that the "
           "information furnished in the application is true and that the institution complies with the norms "
           "and conditions of approval. I undertake to inform the Council of any change.")
    s.gap(10)
    s.line(f"Dated: {d(c['date'])}")
    s.line(f"Notary Reg. No. {c['notary_reg_no']}")
    s.line("Deponent", bold=True, x=400)
    s.footer("Notary Public")
    return s.bytes()


def faculty_list(c: dict) -> bytes:
    doc = fitz.open()
    rows = c["faculty"]
    per_page = 30
    for start in range(0, len(rows), per_page):
        page = doc.new_page(width=A4[0], height=A4[1])
        page.insert_text((60, 60), "FACULTY LIST (TEACHING STAFF)", fontsize=13, fontname="hebo", color=INK)
        page.insert_text((60, 78), c["institution_name"], fontsize=10, fontname="helv", color=MUTED)
        y = 108
        for x, h in zip((60, 150, 330, 450), ("Faculty ID", "Name", "Designation", "Qualification")):
            page.insert_text((x, y), h, fontsize=9.5, fontname="hebo", color=INK)
        y += 18
        for r in rows[start:start + per_page]:
            for x, v in zip((60, 150, 330, 450), (r["faculty_id"], r["name"], r["designation"], r["qualification"])):
                page.insert_text((x, y), v, fontsize=9, fontname="helv", color=INK)
            y += 21
        page.insert_text((60, 818), FOOT, fontsize=7, fontname="helv", color=MUTED)
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out


def scanned(pdf: bytes, quality: int = 18, blur: float = 1.1, rotate: float = 1.6, seed: int = 3) -> bytes:
    """Turn a clean PDF into a poor phone scan (image-only PDF): the text layer is gone, OCR is needed."""
    rnd = random.Random(seed)
    src = fitz.open(stream=pdf, filetype="pdf")
    out = fitz.open()
    for page in src:
        img = Image.open(io.BytesIO(page.get_pixmap(dpi=110).tobytes("png"))).convert("L")
        img = img.rotate(rotate, expand=True, fillcolor=235).filter(ImageFilter.GaussianBlur(blur))
        px = img.load()
        for _ in range(img.width * img.height // 18):
            x, y = rnd.randrange(img.width), rnd.randrange(img.height)
            px[x, y] = min(255, max(0, px[x, y] + rnd.randint(-90, 90)))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        p = out.new_page(width=A4[0], height=A4[1])
        p.insert_image(p.rect, stream=buf.getvalue())
    src.close()
    data = out.tobytes(deflate=True)
    out.close()
    return data


# ------------------------------------------------------------------ photos --
def lab_photo(seed: int, gps: tuple[float, float] | None, taken: datetime, size=(1280, 860)) -> bytes:
    """A procedurally drawn 'computer lab' photo. Each seed gives a different room layout and lighting."""
    rnd = random.Random(seed * 7919 + 13)
    w, h = size
    horizon = int(h * rnd.uniform(0.28, 0.58))
    wall = tuple(rnd.randint(120, 245) for _ in range(3))
    floor = tuple(rnd.randint(70, 200) for _ in range(3))
    img = Image.new("RGB", size, wall)
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, horizon, w, h], fill=floor)
    side = rnd.choice(["left", "right", "none"])
    if side != "none":  # side wall in perspective
        x = int(w * rnd.uniform(0.12, 0.3))
        shade = tuple(max(0, c - rnd.randint(25, 60)) for c in wall)
        poly = [(0, 0), (x, int(horizon * 0.35)), (x, horizon + 40), (0, h)] if side == "left" else \
            [(w, 0), (w - x, int(horizon * 0.35)), (w - x, horizon + 40), (w, h)]
        dr.polygon(poly, fill=shade)
    for _ in range(rnd.randint(0, 4)):  # windows, boards, notices
        bw, bh = rnd.randint(80, 320), rnd.randint(50, 170)
        x, y = rnd.randint(0, w - bw), rnd.randint(10, max(11, horizon - bh - 10))
        fill = rnd.choice([(205, 228, 242), (245, 245, 240), (60, 90, 70), tuple(rnd.randint(40, 230) for _ in range(3))])
        dr.rectangle([x, y, x + bw, y + bh], fill=fill, outline=(90, 90, 90), width=rnd.randint(2, 6))
    for _ in range(rnd.randint(2, 6)):  # ceiling lights
        x = rnd.randint(0, w - 160)
        dr.rectangle([x, rnd.randint(0, 30), x + rnd.randint(80, 200), rnd.randint(34, 50)], fill=(250, 250, 236))
    layout = rnd.choice(["rows", "islands", "diagonal"])
    desk = tuple(rnd.randint(60, 190) for _ in range(3))
    screen = (rnd.randint(30, 140), rnd.randint(80, 190), rnd.randint(140, 235))
    if layout == "rows":
        for r in range(rnd.randint(2, 5)):
            sc = 0.5 + r * rnd.uniform(0.12, 0.25)
            y = horizon - 20 + int(r * h * rnd.uniform(0.09, 0.15))
            dr.rectangle([20, y + int(70 * sc), w - 20, y + int(95 * sc)], fill=desk)
            n = rnd.randint(4, 10)
            for k in range(n):
                x = 40 + k * (w - 80) // n + rnd.randint(-8, 8)
                mw, mh = int(rnd.randint(70, 110) * sc), int(rnd.randint(50, 75) * sc)
                dr.rectangle([x, y, x + mw, y + mh], fill=(20, 22, 28))
                dr.rectangle([x + 4, y + 4, x + mw - 4, y + mh - 8], fill=screen)
    elif layout == "islands":
        for _ in range(rnd.randint(3, 7)):
            cx, cy = rnd.randint(80, w - 160), rnd.randint(horizon, h - 120)
            tw, th = rnd.randint(120, 260), rnd.randint(60, 110)
            dr.rectangle([cx, cy, cx + tw, cy + th], fill=desk)
            for k in range(rnd.randint(2, 4)):
                x = cx + 10 + k * (tw - 20) // 4
                dr.rectangle([x, cy - 45, x + 42, cy - 8], fill=(20, 22, 28))
                dr.rectangle([x + 3, cy - 42, x + 39, cy - 12], fill=screen)
    else:
        for r in range(rnd.randint(2, 4)):
            y0 = horizon + r * rnd.randint(70, 140)
            dr.polygon([(0, y0 + 120), (w, y0), (w, y0 + 28), (0, y0 + 150)], fill=desk)
            for k in range(rnd.randint(5, 9)):
                t = (k + 0.5) / 9
                x, y = int(t * w), int(y0 + 120 - t * 120) - 55
                s_ = 0.6 + (1 - t) * 0.6
                dr.rectangle([x, y, x + int(70 * s_), y + int(50 * s_)], fill=(20, 22, 28))
                dr.rectangle([x + 3, y + 3, x + int(70 * s_) - 3, y + int(50 * s_) - 6], fill=screen)
    img = img.rotate(rnd.uniform(-4, 4), resample=Image.BICUBIC, fillcolor=wall)
    crop = rnd.uniform(0, 0.08)
    img = img.crop((int(w * crop), int(h * crop), int(w * (1 - crop * 0.5)), int(h * (1 - crop * 0.5)))).resize(size)
    img = img.filter(ImageFilter.GaussianBlur(rnd.uniform(0.6, 1.6)))
    px = img.load()
    for _ in range(w * h // 25):
        x, y = rnd.randrange(w), rnd.randrange(h)
        r, g, b = px[x, y]
        n = rnd.randint(-18, 18)
        px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    return _jpeg_with_exif(img, gps, taken)


def _rational(v: float):
    deg = int(v)
    minutes_f = (v - deg) * 60
    minutes = int(minutes_f)
    seconds = round((minutes_f - minutes) * 60 * 100)
    return ((deg, 1), (minutes, 1), (seconds, 100))


def _jpeg_with_exif(img: Image.Image, gps: tuple[float, float] | None, taken: datetime, software: str = "Camera 2.1") -> bytes:
    stamp = taken.strftime("%Y:%m:%d %H:%M:%S").encode()
    exif = {"0th": {piexif.ImageIFD.Make: b"Synthetic", piexif.ImageIFD.Model: b"Sandbox Cam",
                    piexif.ImageIFD.Software: software.encode(), piexif.ImageIFD.DateTime: stamp},
            "Exif": {piexif.ExifIFD.DateTimeOriginal: stamp}, "GPS": {}}
    if gps:
        lat, lon = gps
        exif["GPS"] = {piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S", piexif.GPSIFD.GPSLatitude: _rational(abs(lat)),
                       piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W", piexif.GPSIFD.GPSLongitude: _rational(abs(lon))}
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88, exif=piexif.dump(exif))
    return buf.getvalue()


def recapture(jpeg: bytes, gps: tuple[float, float] | None, taken: datetime) -> bytes:
    """The same photo re-saved (slightly resized and re-compressed) with different metadata."""
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    img = img.resize((int(img.width * 0.94), int(img.height * 0.94)))
    return _jpeg_with_exif(img, gps, taken)
