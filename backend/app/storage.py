"""Encrypted document storage (AES-256-GCM at rest). Local disk by default."""
import base64
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import get_settings


class EncryptedStore:
    def __init__(self, root: Path, key_b64: str):
        key = base64.urlsafe_b64decode(key_b64)
        if len(key) != 32:
            raise ValueError("PRAMAAN_STORAGE_KEY must decode to 32 bytes")
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.aes = AESGCM(key)

    def _path(self, key: str) -> Path:
        if not key.isalnum():
            raise ValueError("bad storage key")
        return self.root / key[:2] / key

    def put(self, data: bytes) -> str:
        key = hashlib.sha256(os.urandom(16) + data).hexdigest()[:40]
        nonce = os.urandom(12)
        blob = nonce + self.aes.encrypt(nonce, data, key.encode())
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        return key

    def get(self, key: str) -> bytes:
        blob = self._path(key).read_bytes()
        return self.aes.decrypt(blob[:12], blob[12:], key.encode())

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()


_store: EncryptedStore | None = None


def store() -> EncryptedStore:
    global _store
    if _store is None:
        s = get_settings()
        _store = EncryptedStore(s.data_dir / "storage", s.storage_key)
    return _store
