"""Validate PDF digital signatures (PKI) against configured trust roots."""
import asyncio
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import get_settings

log = logging.getLogger("pramaan.signatures")
# pyHanko logs a full traceback when its diff analysis finds an unexplained change; that is an expected result here.
logging.getLogger("pyhanko.sign.diff_analysis").setLevel(logging.CRITICAL)


def trust_roots() -> list:
    """Sandbox CA in development; in production point this at CCA India root certificates."""
    from asn1crypto import pem, x509

    roots = []
    folder = get_settings().data_dir / "trust"
    for path in sorted(Path(folder).glob("*.pem")) if folder.exists() else []:
        data = path.read_bytes()
        if pem.detect(data):
            _, _, data = pem.unarmor(data)
        roots.append(x509.Certificate.load(data))
    return roots


def _validate(sig, vc):
    from pyhanko.sign.validation import validate_pdf_signature

    return validate_pdf_signature(sig, vc, skip_diff=False)


def _validate_anywhere(sig, vc):
    """pyHanko's synchronous API starts its own event loop, so it cannot run inside one (a job run inline by an
    async endpoint); there it runs on a short-lived helper thread instead."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _validate(sig, vc)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_validate, sig, vc).result()


def check_signature(data: bytes) -> dict:
    """Return {present, valid, intact, trusted, modified_after_signing, signer, signed_at, summary}."""
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko_certvalidator import ValidationContext

        reader = PdfFileReader(io.BytesIO(data), strict=False)
        sigs = reader.embedded_signatures
    except Exception as exc:
        return {"present": False, "error": f"could not read signature dictionary: {exc}"[:200]}
    if not sigs:
        return {"present": False}
    sig = sigs[0]
    try:
        vc = ValidationContext(trust_roots=trust_roots(), allow_fetching=False)
        st = _validate_anywhere(sig, vc)
    except Exception as exc:
        log.warning("signature validation error: %s", exc)
        return {"present": True, "valid": False, "intact": False, "trusted": False,
                "modified_after_signing": None, "summary": f"Signature could not be validated: {exc}"[:200]}
    mod_level = getattr(st, "modification_level", None)
    modified = bool(mod_level is not None and mod_level.name not in ("NONE", "LTA_UPDATES", "FORM_FILLING")) \
        or not getattr(st, "docmdp_ok", True)
    signer = None
    try:
        signer = st.signing_cert.subject.native.get("common_name") or st.signing_cert.subject.human_friendly
    except Exception:
        pass
    result = {
        "present": True,
        "intact": bool(st.intact),
        "valid": bool(st.valid),
        "trusted": bool(st.trusted),
        "modified_after_signing": modified,
        "coverage": getattr(getattr(st, "coverage", None), "name", None),
        "signer": signer,
        "signed_at": str(getattr(st, "signer_reported_dt", "") or ""),
    }
    if not result["intact"]:
        result["summary"] = "Signed content was altered: the signature no longer matches the file"
    elif modified:
        result["summary"] = "File was changed after it was signed"
    elif not result["trusted"]:
        result["summary"] = "Signature is intact but the signer is not from a trusted authority"
    else:
        result["summary"] = "Signature valid, from a trusted authority, file unchanged since signing"
    return result
