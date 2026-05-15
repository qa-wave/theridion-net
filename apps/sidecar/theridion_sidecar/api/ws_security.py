"""WS-Security: add OASIS security headers to SOAP envelopes.

Supports UsernameToken (PasswordText + PasswordDigest), Timestamp,
and BinarySecurityToken (X.509v3 certificate).  Builds a
<wsse:Security> header, injects it into the SOAP envelope, sends
the request via httpx, and returns both the secured envelope and
the response.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/soap/ws-security", tags=["ws-security"])

# ----- OASIS WS-Security namespace URIs ------------------------------------

WSSE = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-wssecurity-secext-1.0.xsd"
)
WSU = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-wssecurity-utility-1.0.xsd"
)
SOAP = "http://schemas.xmlsoap.org/soap/envelope/"

PASSWORD_TEXT_TYPE = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-username-token-profile-1.0#PasswordText"
)
PASSWORD_DIGEST_TYPE = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-username-token-profile-1.0#PasswordDigest"
)
NONCE_ENCODING = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-soap-message-security-1.0#Base64Binary"
)
X509_VALUE_TYPE = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-x509-token-profile-1.0#X509v3"
)

# ----- Pydantic models -----------------------------------------------------


class WsSecurityConfig(BaseModel):
    type: Literal["UsernameToken", "Timestamp", "BinarySecurityToken"]
    username: str | None = None
    password: str | None = None
    password_type: Literal["PasswordText", "PasswordDigest"] = "PasswordText"
    add_nonce: bool = True
    add_created: bool = True
    add_timestamp: bool = True
    ttl_seconds: int = 300
    certificate_base64: str | None = None


class WsSecurityRequest(BaseModel):
    url: str
    soap_action: str | None = None
    envelope_xml: str
    security: WsSecurityConfig
    headers: dict[str, str] = Field(default_factory=dict)


class WsSecurityResponse(BaseModel):
    ok: bool
    status: int
    response_xml: str
    secured_envelope: str
    error: str | None = None


# ----- Security header builders --------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _build_username_token(cfg: WsSecurityConfig) -> ET.Element:
    """Build a <wsse:UsernameToken> element."""
    token = ET.Element(f"{{{WSSE}}}UsernameToken")
    ET.SubElement(token, f"{{{WSSE}}}Username").text = cfg.username or ""

    password_el = ET.SubElement(token, f"{{{WSSE}}}Password")

    created_str = _utc_now_iso() if cfg.add_created else ""
    nonce_bytes = uuid.uuid4().bytes
    nonce_b64 = base64.b64encode(nonce_bytes).decode()

    if cfg.password_type == "PasswordDigest":
        # Base64( SHA-1( nonce + created + password ) )
        raw = nonce_bytes + created_str.encode("utf-8") + (cfg.password or "").encode("utf-8")
        digest = base64.b64encode(hashlib.sha1(raw).digest()).decode()  # noqa: S324
        password_el.text = digest
        password_el.set("Type", PASSWORD_DIGEST_TYPE)
    else:
        password_el.text = cfg.password or ""
        password_el.set("Type", PASSWORD_TEXT_TYPE)

    if cfg.add_nonce:
        nonce_el = ET.SubElement(token, f"{{{WSSE}}}Nonce")
        nonce_el.text = nonce_b64
        nonce_el.set("EncodingType", NONCE_ENCODING)

    if cfg.add_created:
        ET.SubElement(token, f"{{{WSU}}}Created").text = created_str

    return token


def _build_timestamp(ttl_seconds: int) -> ET.Element:
    """Build a <wsu:Timestamp> element."""
    now = datetime.now(timezone.utc)
    ts = ET.Element(f"{{{WSU}}}Timestamp")
    ET.SubElement(ts, f"{{{WSU}}}Created").text = now.strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"
    expires = now + timedelta(seconds=ttl_seconds)
    ET.SubElement(ts, f"{{{WSU}}}Expires").text = expires.strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"
    return ts


def _build_binary_security_token(cert_b64: str) -> ET.Element:
    """Build a <wsse:BinarySecurityToken> for X.509v3."""
    bst = ET.Element(f"{{{WSSE}}}BinarySecurityToken")
    bst.set("EncodingType", NONCE_ENCODING)
    bst.set("ValueType", X509_VALUE_TYPE)
    bst.text = cert_b64
    return bst


def build_security_header(cfg: WsSecurityConfig) -> ET.Element:
    """Build the complete <wsse:Security> element."""
    sec = ET.Element(f"{{{WSSE}}}Security")
    sec.set(f"{{{SOAP}}}mustUnderstand", "1")

    if cfg.type == "UsernameToken":
        if cfg.add_timestamp:
            sec.append(_build_timestamp(cfg.ttl_seconds))
        sec.append(_build_username_token(cfg))
    elif cfg.type == "Timestamp":
        sec.append(_build_timestamp(cfg.ttl_seconds))
    elif cfg.type == "BinarySecurityToken":
        if cfg.add_timestamp:
            sec.append(_build_timestamp(cfg.ttl_seconds))
        sec.append(_build_binary_security_token(cfg.certificate_base64 or ""))
    return sec


# ----- Envelope injection --------------------------------------------------


# Register namespace prefixes so serialised XML is human-friendly.
ET.register_namespace("wsse", WSSE)
ET.register_namespace("wsu", WSU)
ET.register_namespace("soap", SOAP)
ET.register_namespace("soapenv", SOAP)


def inject_security(envelope_xml: str, cfg: WsSecurityConfig) -> str:
    """Parse a SOAP envelope, inject a <wsse:Security> header, and
    return the modified XML as a string."""
    # Parse — tolerate common namespace prefixes
    root = ET.fromstring(envelope_xml)  # noqa: S314

    # Determine the SOAP namespace actually used in the document
    soap_ns = SOAP
    if root.tag.startswith("{"):
        soap_ns = root.tag.split("}")[0][1:]

    # Find or create <soap:Header>
    header = root.find(f"{{{soap_ns}}}Header")
    if header is None:
        header = ET.Element(f"{{{soap_ns}}}Header")
        root.insert(0, header)

    header.append(build_security_header(cfg))

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


# ----- Route ---------------------------------------------------------------


@router.post("/execute", response_model=WsSecurityResponse)
async def ws_security_execute(body: WsSecurityRequest) -> WsSecurityResponse:
    """Inject WS-Security header into the envelope and send the SOAP request."""
    try:
        secured = inject_security(body.envelope_xml, body.security)
    except ET.ParseError as exc:
        raise HTTPException(status_code=422, detail=f"Malformed SOAP envelope: {exc}") from exc

    send_headers: dict[str, str] = {
        "Content-Type": "text/xml; charset=utf-8",
        **body.headers,
    }
    if body.soap_action:
        send_headers["SOAPAction"] = body.soap_action

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(body.url, content=secured, headers=send_headers)
        return WsSecurityResponse(
            ok=resp.status_code < 500,
            status=resp.status_code,
            response_xml=resp.text,
            secured_envelope=secured,
        )
    except Exception as exc:
        return WsSecurityResponse(
            ok=False,
            status=0,
            response_xml="",
            secured_envelope=secured,
            error=str(exc),
        )
