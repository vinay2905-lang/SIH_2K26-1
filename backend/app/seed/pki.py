"""Sandbox PKI: a root CA and a signing certificate for synthetic, digitally signed certificates."""
import io
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fitz
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PRAMAAN Sandbox"),
                      x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _pem_key(key) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def create_pki(folder: Path, trust_folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    trust_folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc) - timedelta(days=3650)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca = (x509.CertificateBuilder().subject_name(_name("PRAMAAN Sandbox Root CA")).issuer_name(_name("PRAMAAN Sandbox Root CA"))
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now).not_valid_after(now + timedelta(days=365 * 30))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                       data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                                       encipher_only=False, decipher_only=False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    signer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signer = (x509.CertificateBuilder().subject_name(_name("Municipal Corporation Building Permissions (Sandbox)"))
              .issuer_name(ca.subject).public_key(signer_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now).not_valid_after(now + timedelta(days=365 * 25))
              .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
              .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                           data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                           crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
              .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False)
              .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
              .sign(ca_key, hashes.SHA256()))
    files = {"ca_cert": folder / "ca.pem", "ca_key": folder / "ca.key", "signer_cert": folder / "signer.pem",
             "signer_key": folder / "signer.key"}
    files["ca_cert"].write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    files["ca_key"].write_bytes(_pem_key(ca_key))
    files["signer_cert"].write_bytes(signer.public_bytes(serialization.Encoding.PEM))
    files["signer_key"].write_bytes(_pem_key(signer_key))
    (trust_folder / "sandbox-root.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    return files


def sign_pdf(pdf: bytes, files: dict) -> bytes:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers

    signer = signers.SimpleSigner.load(str(files["signer_key"]), str(files["signer_cert"]),
                                       ca_chain_files=(str(files["ca_cert"]),))
    writer = IncrementalPdfFileWriter(io.BytesIO(pdf), strict=False)
    out = signers.sign_pdf(writer, signers.PdfSignatureMetadata(field_name="Signature1", reason="Issued",
                                                                location="Sandbox"), signer=signer)
    return out.getvalue()


def modify_after_signing(signed: bytes, old: str, new: str) -> bytes:
    """Change visible content after signing (an incremental update the signature does not cover)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "s.pdf"
        path.write_bytes(signed)
        doc = fitz.open(path)
        page = doc[0]
        for r in page.search_for(old):
            page.draw_rect(fitz.Rect(r.x0 - 1, r.y0 - 1, r.x1 + 1, r.y1 + 1), color=(1, 1, 1), fill=(1, 1, 1))
            page.insert_text((r.x0, r.y1 - 2.2), new, fontsize=10, fontname="hebo", color=(0.11, 0.13, 0.2))
        doc.saveIncr()
        doc.close()
        return path.read_bytes()
