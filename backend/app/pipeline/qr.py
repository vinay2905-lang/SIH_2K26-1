"""Decode QR codes printed on certificates."""
import io

import cv2
import fitz
import numpy as np
from PIL import Image

from .ingest import sniff_kind


def _decode(img: Image.Image) -> str | None:
    arr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    det = cv2.QRCodeDetector()
    for scale in (1.0, 0.6, 1.5):
        a = arr if scale == 1.0 else cv2.resize(arr, None, fx=scale, fy=scale)
        try:
            ok, values, _, _ = det.detectAndDecodeMulti(a)
        except cv2.error:
            ok, values = False, []
        if ok:
            for v in values:
                if v:
                    return v
        value, _, _ = det.detectAndDecode(a)
        if value:
            return value
    return None


def read_qr(data: bytes) -> str | None:
    kind = sniff_kind(data)
    if kind == "image":
        return _decode(Image.open(io.BytesIO(data)))
    if kind != "pdf":
        return None
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        for page in list(doc)[:2]:
            pix = page.get_pixmap(dpi=200)
            value = _decode(Image.open(io.BytesIO(pix.tobytes("png"))))
            if value:
                return value
    finally:
        doc.close()
    return None
