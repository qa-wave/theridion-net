"""REST API for the secrets vault.

Secrets are Fernet-encrypted at rest.  These endpoints allow the FE
(SecretsVaultModal) to store, list, delete, and verify secrets.  The
plaintext value is accepted on write and discarded after encryption;
it is **never** returned on read (only existence is confirmed).

Endpoints:
  GET    /api/vault/secrets           — list secret names
  POST   /api/vault/secrets           — store (or overwrite) a secret
  DELETE /api/vault/secrets/{name}    — delete a secret
  GET    /api/vault/secrets/{name}/exists — check existence without revealing value
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import secrets_vault as vault

router = APIRouter(prefix="/api/vault", tags=["secrets-vault"])


class StoreSecretInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    # The plaintext value — held in memory only long enough to encrypt.
    value: str = Field(..., min_length=0, max_length=65536)


class SecretExistsOutput(BaseModel):
    name: str
    exists: bool


class SecretNamesOutput(BaseModel):
    names: list[str]


@router.get("/secrets", response_model=SecretNamesOutput)
def list_secrets() -> SecretNamesOutput:
    """Return all stored secret names.  Values are never exposed."""
    return SecretNamesOutput(names=vault.list_names())


@router.post("/secrets", status_code=201)
def store_secret(body: StoreSecretInput) -> dict[str, str]:
    """Encrypt and persist a secret value.  Overwrites if it already exists."""
    try:
        vault.store(body.name, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Do NOT echo back the value.
    return {"name": body.name, "status": "stored"}


@router.delete("/secrets/{name}", status_code=204)
def delete_secret(name: str) -> None:
    """Remove a secret from the vault."""
    deleted = vault.delete(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="secret not found")


@router.get("/secrets/{name}/exists", response_model=SecretExistsOutput)
def secret_exists(name: str) -> SecretExistsOutput:
    """Check whether a secret exists without returning its value."""
    return SecretExistsOutput(name=name, exists=name in vault.list_names())
