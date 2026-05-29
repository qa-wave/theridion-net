"""Secrets vault: encrypted at-rest storage for sensitive values.

Secrets are Fernet-encrypted using a key derived from a machine-local
passphrase (or THERIDION_VAULT_PASSPHRASE env var for tests).  The
encrypted blobs are stored in::

    $THERIDION_HOME/secrets/<name>.enc

The file name is the secret name, the content is the base64-encoded
``salt(16 bytes) + ciphertext`` produced by :func:`_derive_fernet_key`.

Critically:
- Plaintext secret values are NEVER written to disk.
- Secret values are NEVER logged (callers must take care of this).
- Resolution happens at request-send time only (not at env-load time).
"""

from __future__ import annotations

import base64
import logging
import os
import re
import stat
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .storage import home_dir

logger = logging.getLogger(__name__)

# Pattern for valid secret names: alphanumeric + underscore + dash
_SECRET_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,127}$")

# Sentinel returned when a secret is not found (not the actual value)
_MISSING = object()


def _vault_dir() -> Path:
    d = home_dir() / "secrets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path_for(name: str) -> Path:
    if not _SECRET_NAME_RE.match(name):
        raise ValueError(f"invalid secret name: {name!r}")
    return _vault_dir() / f"{name}.enc"


def _get_passphrase() -> bytes:
    """Return the vault passphrase bytes.

    Preference order:
    1. THERIDION_VAULT_PASSPHRASE env var (for tests / CI)
    2. Machine-local token file ~/.theridion/vault-key (auto-created, chmod 600)
    """
    env_pass = os.environ.get("THERIDION_VAULT_PASSPHRASE")
    if env_pass:
        return env_pass.encode("utf-8")

    key_path = home_dir() / "vault-key"
    if key_path.exists():
        return key_path.read_bytes().strip()

    # First run: generate a random 32-byte hex key and persist it.
    import secrets as _secrets

    raw = _secrets.token_hex(32)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(dir=str(key_path.parent), suffix=".tmp")
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, key_path)
        key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return raw.encode("utf-8")


def _derive_fernet_key(passphrase: bytes, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase))


def store(name: str, plaintext: str) -> None:
    """Encrypt *plaintext* and persist as ``secrets/<name>.enc``.

    The plaintext is never written to disk.  The passphrase is derived
    from the machine-local vault key.
    """
    passphrase = _get_passphrase()
    salt = os.urandom(16)
    key = _derive_fernet_key(passphrase, salt)
    f = Fernet(key)
    ciphertext = f.encrypt(plaintext.encode("utf-8"))
    blob = base64.b64encode(salt + ciphertext)

    path = _path_for(name)
    fd, tmp_str = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def resolve(name: str) -> str | None:
    """Decrypt and return the secret named *name*, or ``None`` if not found.

    Returns ``None`` on missing file or decryption failure.
    NEVER logs the plaintext value.
    """
    try:
        path = _path_for(name)
    except ValueError:
        logger.warning("vault resolve: invalid secret name requested")
        return None

    if not path.exists():
        return None

    try:
        blob = base64.b64decode(path.read_bytes())
        salt = blob[:16]
        ciphertext = blob[16:]
        passphrase = _get_passphrase()
        key = _derive_fernet_key(passphrase, salt)
        f = Fernet(key)
        return f.decrypt(ciphertext).decode("utf-8")
    except (InvalidToken, Exception):
        # Do NOT log the exception detail — it may contain partial secret data.
        logger.warning("vault resolve: failed to decrypt secret %r", name)
        return None


def delete(name: str) -> bool:
    """Remove secret *name* from vault. Returns True if it existed."""
    try:
        path = _path_for(name)
    except ValueError:
        return False
    if not path.exists():
        return False
    path.unlink()
    return True


def list_names() -> list[str]:
    """Return all stored secret names (no values)."""
    out: list[str] = []
    for p in sorted(_vault_dir().glob("*.enc")):
        out.append(p.stem)
    return out
