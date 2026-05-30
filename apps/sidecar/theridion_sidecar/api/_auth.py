"""Shared authentication injection helper.

Extracted from api/requests.py so that loadtest, multipart, chaining,
pipeline, runner, cli_runner and any future modules can all use the same
implementation (DRY).
"""

from __future__ import annotations

import base64

from .. import environments
from ..models import AuthConfig


def apply_auth(
    auth: AuthConfig,
    headers: dict[str, str],
    query: dict[str, str],
    env: environments.Environment | None,
    collection_vars: dict[str, str] | None = None,
) -> None:
    """Mutate *headers* or *query* in-place to inject auth credentials.

    Supports bearer, basic, and apikey schemes.  Variable placeholders
    (``{{var}}``) inside credential strings are resolved against *env* and
    *collection_vars* before injection.
    """
    sub = (
        lambda v: environments.substitute(v, env, collection_vars=collection_vars)
        if v
        else ""
    )
    if auth.type == "bearer":
        headers["Authorization"] = f"Bearer {sub(auth.token)}"
    elif auth.type == "basic":
        creds = base64.b64encode(
            f"{sub(auth.username)}:{sub(auth.password)}".encode()
        ).decode()
        headers["Authorization"] = f"Basic {creds}"
    elif auth.type == "apikey":
        key = sub(auth.key)
        value = sub(auth.value)
        if key:
            if auth.add_to == "query":
                query[key] = value
            else:
                headers[key] = value
