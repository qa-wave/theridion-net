"""First-run seed data for Theridion Net.

Populates the local storage with realistic demo data so the Integration,
History, Load and Security panels are populated on first run without requiring
any external network calls or manual setup.

Idempotency contract:
- Collections are seeded only when ``collections_dir()`` contains **no** JSON files.
- History is seeded only when ``history.jsonl`` does not exist or is empty.
- Load results are seeded only when ``load_results.jsonl`` does not exist or is empty.
- Security scans are seeded only when ``security_scans.jsonl`` does not exist or is empty.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fixed UUIDs so the seed is deterministic and can be referenced cross-module
# ---------------------------------------------------------------------------

# Collections
_COL_REST_ID = "a1b2c3d4-0001-4000-8000-000000000001"
_COL_GRAPHQL_ID = "a1b2c3d4-0002-4000-8000-000000000002"
_COL_GRPC_ID = "a1b2c3d4-0003-4000-8000-000000000003"
_COL_SOAP_ID = "a1b2c3d4-0004-4000-8000-000000000004"

# REST collection request ids (for cross-referencing history entries)
_REQ_GET_USERS = "b1000001-0001-4000-8000-000000000001"
_REQ_CREATE_USER = "b1000001-0002-4000-8000-000000000002"
_REQ_GET_USER = "b1000001-0003-4000-8000-000000000003"
_REQ_UPDATE_USER = "b1000001-0004-4000-8000-000000000004"
_REQ_DELETE_USER = "b1000001-0005-4000-8000-000000000005"
_REQ_GET_PRODUCTS = "b1000001-0006-4000-8000-000000000006"
_REQ_GET_PRODUCT = "b1000001-0007-4000-8000-000000000007"
_REQ_PLACE_ORDER = "b1000001-0008-4000-8000-000000000008"
_REQ_GET_ORDERS = "b1000001-0009-4000-8000-000000000009"
_REQ_HEALTHCHECK = "b1000001-000a-4000-8000-000000000010"

# Folder ids
_FOLDER_USERS = "f1000001-0001-4000-8000-000000000001"
_FOLDER_PRODUCTS = "f1000001-0002-4000-8000-000000000002"
_FOLDER_ORDERS = "f1000001-0003-4000-8000-000000000003"


# ---------------------------------------------------------------------------
# Timestamp helpers — spread over recent weeks
# ---------------------------------------------------------------------------

def _ts(days_ago: float, hour: int = 10, minute: int = 0) -> float:
    """Return a Unix timestamp for *days_ago* days in the past."""
    import time as _time
    now = _time.time()
    return now - days_ago * 86400 + hour * 3600 + minute * 60


# ---------------------------------------------------------------------------
# Collections seed
# ---------------------------------------------------------------------------

def _seed_collections(collections_dir: Path) -> None:
    """Write four demo collections if the directory is empty."""
    existing = list(collections_dir.glob("*.json"))
    if existing:
        return

    logger.info("Seeding demo collections…")

    # 1. REST — E-Commerce API -----------------------------------------------
    rest_collection = {
        "id": _COL_REST_ID,
        "name": "E-Commerce API",
        "version": 1,
        "variables": [
            {"name": "base_url", "value": "https://api.shop.example.com/v2", "enabled": True},
            {"name": "api_key", "value": "sk_test_demo_key_12345", "enabled": True},
        ],
        "items": [
            {
                "id": _FOLDER_USERS,
                "name": "Users",
                "is_folder": True,
                "kind": "request",
                "method": None,
                "url": None,
                "headers": {},
                "body": None,
                "auth": None,
                "assertions": [],
                "tags": [],
                "examples": [],
                "captures": [],
                "notes": "User management endpoints",
                "items": [
                    {
                        "id": _REQ_GET_USERS,
                        "name": "List Users",
                        "is_folder": False,
                        "kind": "request",
                        "method": "GET",
                        "url": "{{base_url}}/users?page=1&limit=20",
                        "headers": {
                            "Accept": "application/json",
                            "X-API-Key": "{{api_key}}",
                        },
                        "body": None,
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                            {"type": "response_time", "expected": "500", "path": "", "operator": "eq"},
                            {"type": "json_path", "expected": "true", "path": "success", "operator": "eq"},
                            {"type": "json_path", "expected": "", "path": "data", "operator": "exists"},
                        ],
                        "captures": [
                            {"name": "first_user_id", "source": "body", "path": "data[0].id"},
                        ],
                        "tags": ["users", "list"],
                        "examples": [],
                        "notes": "Returns paginated list of all registered users.",
                        "items": [],
                    },
                    {
                        "id": _REQ_CREATE_USER,
                        "name": "Create User",
                        "is_folder": False,
                        "kind": "request",
                        "method": "POST",
                        "url": "{{base_url}}/users",
                        "headers": {
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                            "X-API-Key": "{{api_key}}",
                        },
                        "body": json.dumps({
                            "email": "alice@example.com",
                            "first_name": "Alice",
                            "last_name": "Wonderland",
                            "role": "customer",
                        }, indent=2),
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "201", "path": "", "operator": "eq"},
                            {"type": "json_path", "expected": "", "path": "id", "operator": "exists"},
                            {"type": "json_path", "expected": "alice@example.com", "path": "email", "operator": "eq"},
                            {"type": "header_exists", "expected": "", "path": "Location", "operator": "eq"},
                        ],
                        "captures": [
                            {"name": "new_user_id", "source": "body", "path": "id"},
                        ],
                        "tags": ["users", "create"],
                        "examples": [],
                        "notes": "Creates a new user account.",
                        "items": [],
                    },
                    {
                        "id": _REQ_GET_USER,
                        "name": "Get User by ID",
                        "is_folder": False,
                        "kind": "request",
                        "method": "GET",
                        "url": "{{base_url}}/users/{{first_user_id}}",
                        "headers": {
                            "Accept": "application/json",
                            "X-API-Key": "{{api_key}}",
                        },
                        "body": None,
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                            {"type": "json_path", "expected": "", "path": "id", "operator": "exists"},
                            {"type": "json_path", "expected": "customer", "path": "role", "operator": "eq"},
                        ],
                        "captures": [],
                        "tags": ["users"],
                        "examples": [],
                        "notes": "Fetches a single user by their UUID.",
                        "items": [],
                    },
                    {
                        "id": _REQ_UPDATE_USER,
                        "name": "Update User",
                        "is_folder": False,
                        "kind": "request",
                        "method": "PATCH",
                        "url": "{{base_url}}/users/{{first_user_id}}",
                        "headers": {
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                            "X-API-Key": "{{api_key}}",
                        },
                        "body": json.dumps({"last_name": "Smith", "role": "admin"}, indent=2),
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                            {"type": "json_path", "expected": "Smith", "path": "last_name", "operator": "eq"},
                        ],
                        "captures": [],
                        "tags": ["users", "update"],
                        "examples": [],
                        "notes": None,
                        "items": [],
                    },
                    {
                        "id": _REQ_DELETE_USER,
                        "name": "Delete User",
                        "is_folder": False,
                        "kind": "request",
                        "method": "DELETE",
                        "url": "{{base_url}}/users/{{first_user_id}}",
                        "headers": {
                            "X-API-Key": "{{api_key}}",
                        },
                        "body": None,
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "204", "path": "", "operator": "eq"},
                        ],
                        "captures": [],
                        "tags": ["users", "delete"],
                        "examples": [],
                        "notes": "Soft-deletes a user. Responds 204 No Content on success.",
                        "items": [],
                    },
                ],
            },
            {
                "id": _FOLDER_PRODUCTS,
                "name": "Products",
                "is_folder": True,
                "kind": "request",
                "method": None,
                "url": None,
                "headers": {},
                "body": None,
                "auth": None,
                "assertions": [],
                "tags": [],
                "examples": [],
                "captures": [],
                "notes": "Product catalogue endpoints",
                "items": [
                    {
                        "id": _REQ_GET_PRODUCTS,
                        "name": "List Products",
                        "is_folder": False,
                        "kind": "request",
                        "method": "GET",
                        "url": "{{base_url}}/products?category=electronics&in_stock=true",
                        "headers": {"Accept": "application/json"},
                        "body": None,
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                            {"type": "json_path", "expected": "true", "path": "success", "operator": "eq"},
                            {"type": "json_path", "expected": "0", "path": "total", "operator": "gt"},
                        ],
                        "captures": [
                            {"name": "product_id", "source": "body", "path": "data[0].sku"},
                        ],
                        "tags": ["products"],
                        "examples": [],
                        "notes": "Returns in-stock electronics filtered by category.",
                        "items": [],
                    },
                    {
                        "id": _REQ_GET_PRODUCT,
                        "name": "Get Product Detail",
                        "is_folder": False,
                        "kind": "request",
                        "method": "GET",
                        "url": "{{base_url}}/products/{{product_id}}",
                        "headers": {"Accept": "application/json"},
                        "body": None,
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                            {"type": "json_path", "expected": "", "path": "price", "operator": "exists"},
                            {"type": "json_path", "expected": "0", "path": "price", "operator": "gt"},
                        ],
                        "captures": [],
                        "tags": ["products"],
                        "examples": [],
                        "notes": None,
                        "items": [],
                    },
                ],
            },
            {
                "id": _FOLDER_ORDERS,
                "name": "Orders",
                "is_folder": True,
                "kind": "request",
                "method": None,
                "url": None,
                "headers": {},
                "body": None,
                "auth": None,
                "assertions": [],
                "tags": [],
                "examples": [],
                "captures": [],
                "notes": "Order lifecycle endpoints",
                "items": [
                    {
                        "id": _REQ_PLACE_ORDER,
                        "name": "Place Order",
                        "is_folder": False,
                        "kind": "request",
                        "method": "POST",
                        "url": "{{base_url}}/orders",
                        "headers": {
                            "Content-Type": "application/json",
                            "Authorization": "Bearer {{api_key}}",
                        },
                        "body": json.dumps({
                            "user_id": "usr_1234",
                            "items": [
                                {"sku": "ELEC-001", "qty": 2, "unit_price": 49.99},
                                {"sku": "ELEC-002", "qty": 1, "unit_price": 129.00},
                            ],
                            "shipping_address": {
                                "street": "123 Main St",
                                "city": "Prague",
                                "country": "CZ",
                                "zip": "11000",
                            },
                        }, indent=2),
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "201", "path": "", "operator": "eq"},
                            {"type": "json_path", "expected": "", "path": "order_id", "operator": "exists"},
                            {"type": "json_path", "expected": "pending", "path": "status", "operator": "eq"},
                            {"type": "response_time", "expected": "1000", "path": "", "operator": "eq"},
                        ],
                        "captures": [
                            {"name": "order_id", "source": "body", "path": "order_id"},
                        ],
                        "tags": ["orders", "create"],
                        "examples": [],
                        "notes": "Creates a new order for the authenticated user.",
                        "items": [],
                    },
                    {
                        "id": _REQ_GET_ORDERS,
                        "name": "List Orders",
                        "is_folder": False,
                        "kind": "request",
                        "method": "GET",
                        "url": "{{base_url}}/orders?status=pending&limit=10",
                        "headers": {
                            "Accept": "application/json",
                            "Authorization": "Bearer {{api_key}}",
                        },
                        "body": None,
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                        ],
                        "captures": [],
                        "tags": ["orders"],
                        "examples": [],
                        "notes": None,
                        "items": [],
                    },
                ],
            },
            {
                "id": _REQ_HEALTHCHECK,
                "name": "Health Check",
                "is_folder": False,
                "kind": "request",
                "method": "GET",
                "url": "{{base_url}}/health",
                "headers": {"Accept": "application/json"},
                "body": None,
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                    {"type": "json_path", "expected": "ok", "path": "status", "operator": "eq"},
                    {"type": "response_time", "expected": "200", "path": "", "operator": "eq"},
                ],
                "captures": [],
                "tags": ["health"],
                "examples": [],
                "notes": "Liveness probe — used in CI gating.",
                "items": [],
            },
        ],
    }

    # 2. GraphQL — GitHub-style API ------------------------------------------
    graphql_collection = {
        "id": _COL_GRAPHQL_ID,
        "name": "GitHub GraphQL API",
        "version": 1,
        "variables": [
            {"name": "endpoint", "value": "https://api.github.com/graphql", "enabled": True},
            {"name": "token", "value": "ghp_demo_token_replace_me", "enabled": True},
        ],
        "items": [
            {
                "id": str(uuid.UUID("c1000002-0001-4000-8000-000000000001")),
                "name": "Get Viewer Profile",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{endpoint}}",
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "bearer {{token}}",
                },
                "body": json.dumps({
                    "query": "query { viewer { login name email bio url followers { totalCount } } }",
                }, indent=2),
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                    {"type": "json_path", "expected": "", "path": "data.viewer", "operator": "exists"},
                ],
                "captures": [
                    {"name": "viewer_login", "source": "body", "path": "data.viewer.login"},
                ],
                "tags": ["graphql", "viewer"],
                "examples": [],
                "notes": "Fetches the authenticated user's profile.",
                "items": [],
            },
            {
                "id": str(uuid.UUID("c1000002-0002-4000-8000-000000000002")),
                "name": "List Repositories",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{endpoint}}",
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "bearer {{token}}",
                },
                "body": json.dumps({
                    "query": """query($login: String!, $first: Int!) {
  user(login: $login) {
    repositories(first: $first, orderBy: {field: STARGAZERS, direction: DESC}) {
      nodes { name description stargazerCount forkCount isPrivate }
    }
  }
}""",
                    "variables": {"login": "{{viewer_login}}", "first": 10},
                }, indent=2),
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                    {"type": "json_path", "expected": "", "path": "data.user.repositories.nodes", "operator": "exists"},
                ],
                "captures": [],
                "tags": ["graphql", "repositories"],
                "examples": [],
                "notes": "Lists top-10 repos sorted by stars.",
                "items": [],
            },
            {
                "id": str(uuid.UUID("c1000002-0003-4000-8000-000000000003")),
                "name": "Create Issue (Mutation)",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{endpoint}}",
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "bearer {{token}}",
                },
                "body": json.dumps({
                    "query": """mutation($repoId: ID!, $title: String!, $body: String) {
  createIssue(input: {repositoryId: $repoId, title: $title, body: $body}) {
    issue { number url state }
  }
}""",
                    "variables": {
                        "repoId": "R_kgDOABCD1234",
                        "title": "Demo issue from Theridion",
                        "body": "Created via GraphQL mutation during API testing.",
                    },
                }, indent=2),
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                    {"type": "json_path", "expected": "", "path": "data.createIssue.issue.number", "operator": "exists"},
                ],
                "captures": [
                    {"name": "issue_number", "source": "body", "path": "data.createIssue.issue.number"},
                ],
                "tags": ["graphql", "mutation"],
                "examples": [],
                "notes": "Requires write scope on the token.",
                "items": [],
            },
        ],
    }

    # 3. gRPC — User Service -------------------------------------------------
    grpc_collection = {
        "id": _COL_GRPC_ID,
        "name": "User Service (gRPC)",
        "version": 1,
        "variables": [
            {"name": "grpc_host", "value": "users.internal.example.com:50051", "enabled": True},
        ],
        "items": [
            {
                "id": str(uuid.UUID("d1000003-0001-4000-8000-000000000001")),
                "name": "GetUser RPC",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{grpc_host}}",
                "headers": {"content-type": "application/grpc+json"},
                "body": json.dumps({
                    "_grpc_method": "user.UserService/GetUser",
                    "user_id": "usr_7f4a1b2c",
                }),
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                    {"type": "json_path", "expected": "", "path": "user_id", "operator": "exists"},
                ],
                "captures": [],
                "tags": ["grpc", "users"],
                "examples": [],
                "notes": "GetUser unary RPC — proto: user.UserService.",
                "items": [],
            },
            {
                "id": str(uuid.UUID("d1000003-0002-4000-8000-000000000002")),
                "name": "ListUsers RPC",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{grpc_host}}",
                "headers": {"content-type": "application/grpc+json"},
                "body": json.dumps({
                    "_grpc_method": "user.UserService/ListUsers",
                    "page_size": 20,
                    "page_token": "",
                }),
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                ],
                "captures": [
                    {"name": "next_page_token", "source": "body", "path": "next_page_token"},
                ],
                "tags": ["grpc", "users", "pagination"],
                "examples": [],
                "notes": "Server-streaming RPC with pagination token.",
                "items": [],
            },
            {
                "id": str(uuid.UUID("d1000003-0003-4000-8000-000000000003")),
                "name": "UpdateUser RPC",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{grpc_host}}",
                "headers": {"content-type": "application/grpc+json"},
                "body": json.dumps({
                    "_grpc_method": "user.UserService/UpdateUser",
                    "user_id": "usr_7f4a1b2c",
                    "display_name": "Alice Smith",
                    "phone": "+1-555-0100",
                }),
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                    {"type": "json_path", "expected": "usr_7f4a1b2c", "path": "user_id", "operator": "eq"},
                ],
                "captures": [],
                "tags": ["grpc", "users", "update"],
                "examples": [],
                "notes": None,
                "items": [],
            },
        ],
    }

    # 4. SOAP — Payment Gateway ----------------------------------------------
    soap_collection = {
        "id": _COL_SOAP_ID,
        "name": "Payment Gateway (SOAP)",
        "version": 1,
        "variables": [
            {"name": "wsdl_url", "value": "https://payments.example.com/ws/v3?wsdl", "enabled": True},
            {"name": "merchant_id", "value": "MERCH_DEMO_9876", "enabled": True},
            {"name": "secret_key", "value": "s3cr3tK3y_replace_in_production", "enabled": True},
        ],
        "items": [
            {
                "id": str(uuid.UUID("e1000004-0001-4000-8000-000000000001")),
                "name": "AuthorizeCard",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{wsdl_url}}",
                "headers": {
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": "\"urn:AuthorizeCard\"",
                },
                "body": """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:pay="urn:payment.example.com:v3">
  <soapenv:Header>
    <pay:Security>
      <pay:MerchantId>{{merchant_id}}</pay:MerchantId>
      <pay:Timestamp>2024-05-15T10:30:00Z</pay:Timestamp>
      <pay:Signature>{{secret_key}}</pay:Signature>
    </pay:Security>
  </soapenv:Header>
  <soapenv:Body>
    <pay:AuthorizeCardRequest>
      <pay:Amount>99.99</pay:Amount>
      <pay:Currency>USD</pay:Currency>
      <pay:Card>
        <pay:Pan>4111111111111111</pay:Pan>
        <pay:Expiry>12/26</pay:Expiry>
        <pay:Cvv>123</pay:Cvv>
      </pay:Card>
    </pay:AuthorizeCardRequest>
  </soapenv:Body>
</soapenv:Envelope>""",
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                    {"type": "body_contains", "expected": "AuthorizeCardResponse", "path": "", "operator": "eq"},
                    {"type": "body_contains", "expected": "APPROVED", "path": "", "operator": "eq"},
                ],
                "captures": [
                    {"name": "auth_code", "source": "body", "path": "AuthCode"},
                ],
                "tags": ["soap", "payment", "authorize"],
                "examples": [],
                "notes": "WS-Security signed authorization request. Replace test card with sandbox credentials.",
                "items": [],
            },
            {
                "id": str(uuid.UUID("e1000004-0002-4000-8000-000000000002")),
                "name": "CapturePayment",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{wsdl_url}}",
                "headers": {
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": "\"urn:CapturePayment\"",
                },
                "body": """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:pay="urn:payment.example.com:v3">
  <soapenv:Header>
    <pay:Security>
      <pay:MerchantId>{{merchant_id}}</pay:MerchantId>
      <pay:Timestamp>2024-05-15T10:35:00Z</pay:Timestamp>
      <pay:Signature>{{secret_key}}</pay:Signature>
    </pay:Security>
  </soapenv:Header>
  <soapenv:Body>
    <pay:CapturePaymentRequest>
      <pay:AuthCode>{{auth_code}}</pay:AuthCode>
      <pay:Amount>99.99</pay:Amount>
    </pay:CapturePaymentRequest>
  </soapenv:Body>
</soapenv:Envelope>""",
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                    {"type": "body_contains", "expected": "CAPTURED", "path": "", "operator": "eq"},
                ],
                "captures": [
                    {"name": "transaction_id", "source": "body", "path": "TransactionId"},
                ],
                "tags": ["soap", "payment", "capture"],
                "examples": [],
                "notes": "Capture a previously authorized payment. Requires auth_code from AuthorizeCard.",
                "items": [],
            },
            {
                "id": str(uuid.UUID("e1000004-0003-4000-8000-000000000003")),
                "name": "RefundPayment",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{wsdl_url}}",
                "headers": {
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": "\"urn:RefundPayment\"",
                },
                "body": """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:pay="urn:payment.example.com:v3">
  <soapenv:Header>
    <pay:Security>
      <pay:MerchantId>{{merchant_id}}</pay:MerchantId>
    </pay:Security>
  </soapenv:Header>
  <soapenv:Body>
    <pay:RefundPaymentRequest>
      <pay:TransactionId>{{transaction_id}}</pay:TransactionId>
      <pay:Amount>99.99</pay:Amount>
      <pay:Reason>Customer requested refund</pay:Reason>
    </pay:RefundPaymentRequest>
  </soapenv:Body>
</soapenv:Envelope>""",
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                    {"type": "body_contains", "expected": "REFUNDED", "path": "", "operator": "eq"},
                ],
                "captures": [],
                "tags": ["soap", "payment", "refund"],
                "examples": [],
                "notes": None,
                "items": [],
            },
        ],
    }

    for col_data in [rest_collection, graphql_collection, grpc_collection, soap_collection]:
        col_id = col_data["id"]
        col_path = collections_dir / f"{col_id}.json"
        _atomic_json_write(col_path, col_data)
        logger.info("  Seeded collection: %s (%s)", col_data["name"], col_id)


# ---------------------------------------------------------------------------
# History seed
# ---------------------------------------------------------------------------

def _seed_history(history_path: Path) -> None:
    """Write demo request history if the file does not exist or is empty."""
    if history_path.exists() and history_path.stat().st_size > 0:
        return

    logger.info("Seeding demo history…")

    # Use str(uuid.uuid4())-style fixed strings that are valid hex UUIDs
    entries: list[dict[str, Any]] = [
        # --- Week 1 ---
        {
            "id": "a0000001-0001-4000-8000-000000000001",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/users?page=1&limit=20",
            "status": 200,
            "elapsed_ms": 87.3,
            "timestamp": _ts(12, 14, 22),
            "request_headers": {"Accept": "application/json", "X-API-Key": "sk_test_demo_key_12345"},
            "response_headers": {"Content-Type": "application/json", "X-Request-Id": "abc1234"},
            "request_body": None,
            "response_body": '{"success":true,"data":[{"id":"usr_001","email":"alice@example.com"}],"total":42,"page":1}',
        },
        {
            "id": "a0000001-0002-4000-8000-000000000002",
            "method": "POST",
            "url": "https://api.shop.example.com/v2/users",
            "status": 201,
            "elapsed_ms": 143.6,
            "timestamp": _ts(12, 14, 35),
            "request_headers": {"Content-Type": "application/json"},
            "response_headers": {"Content-Type": "application/json", "Location": "/v2/users/usr_new_001"},
            "request_body": '{"email":"alice@example.com","first_name":"Alice","last_name":"Wonderland","role":"customer"}',
            "response_body": '{"id":"usr_new_001","email":"alice@example.com","role":"customer","created_at":"2024-05-14T14:35:00Z"}',
        },
        {
            "id": "a0000001-0003-4000-8000-000000000003",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/products?category=electronics&in_stock=true",
            "status": 200,
            "elapsed_ms": 62.1,
            "timestamp": _ts(11, 9, 15),
            "request_headers": {"Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json", "Cache-Control": "max-age=60"},
            "request_body": None,
            "response_body": '{"success":true,"data":[{"sku":"ELEC-001","name":"Wireless Mouse","price":49.99,"stock":234}],"total":18}',
        },
        {
            "id": "a0000001-0004-4000-8000-000000000004",
            "method": "POST",
            "url": "https://api.shop.example.com/v2/orders",
            "status": 201,
            "elapsed_ms": 312.4,
            "timestamp": _ts(10, 16, 45),
            "request_headers": {"Content-Type": "application/json", "Authorization": "Bearer sk_test_demo_key_12345"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": '{"user_id":"usr_001","items":[{"sku":"ELEC-001","qty":2,"unit_price":49.99}]}',
            "response_body": '{"order_id":"ord_abc123","status":"pending","total":99.98,"created_at":"2024-05-16T16:45:00Z"}',
        },
        {
            "id": "a0000001-0005-4000-8000-000000000005",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/health",
            "status": 200,
            "elapsed_ms": 12.7,
            "timestamp": _ts(9, 8, 0),
            "request_headers": {"Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"status":"ok","version":"2.4.1","db":"connected","redis":"connected"}',
        },
        # --- Week 2 ---
        {
            "id": "a0000001-0006-4000-8000-000000000006",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/users/usr_new_001",
            "status": 200,
            "elapsed_ms": 55.0,
            "timestamp": _ts(8, 11, 30),
            "request_headers": {"Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"id":"usr_new_001","email":"alice@example.com","role":"customer","last_login":"2024-05-18T11:00:00Z"}',
        },
        {
            "id": "a0000001-0007-4000-8000-000000000007",
            "method": "PATCH",
            "url": "https://api.shop.example.com/v2/users/usr_new_001",
            "status": 200,
            "elapsed_ms": 98.2,
            "timestamp": _ts(8, 11, 45),
            "request_headers": {"Content-Type": "application/json"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": '{"last_name":"Smith","role":"admin"}',
            "response_body": '{"id":"usr_new_001","last_name":"Smith","role":"admin"}',
        },
        {
            "id": "a0000001-0008-4000-8000-000000000008",
            "method": "POST",
            "url": "https://api.github.com/graphql",
            "status": 200,
            "elapsed_ms": 185.9,
            "timestamp": _ts(7, 14, 0),
            "request_headers": {"Content-Type": "application/json", "Authorization": "bearer ghp_demo_token"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": '{"query":"query { viewer { login name } }"}',
            "response_body": '{"data":{"viewer":{"login":"alice-dev","name":"Alice Smith"}}}',
        },
        {
            "id": "a0000001-0009-4000-8000-000000000009",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/orders?status=pending&limit=10",
            "status": 200,
            "elapsed_ms": 74.4,
            "timestamp": _ts(6, 10, 20),
            "request_headers": {"Accept": "application/json", "Authorization": "Bearer sk_test_demo_key_12345"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"success":true,"data":[{"order_id":"ord_abc123","status":"pending","total":99.98}],"total":3}',
        },
        {
            "id": "a0000001-000a-4000-8000-00000000000a",
            "method": "POST",
            "url": "https://payments.example.com/ws/v3?wsdl",
            "status": 200,
            "elapsed_ms": 241.0,
            "timestamp": _ts(5, 15, 10),
            "request_headers": {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '"urn:AuthorizeCard"'},
            "response_headers": {"Content-Type": "text/xml; charset=utf-8"},
            "request_body": '<?xml version="1.0"?><soapenv:Envelope>...</soapenv:Envelope>',
            "response_body": '<?xml version="1.0"?><soapenv:Envelope><soapenv:Body><AuthorizeCardResponse><Status>APPROVED</Status><AuthCode>AUTH_7791</AuthCode></AuthorizeCardResponse></soapenv:Body></soapenv:Envelope>',
        },
        # --- Recent (last 4 days) ---
        {
            "id": "a0000001-000b-4000-8000-00000000000b",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/health",
            "status": 200,
            "elapsed_ms": 11.3,
            "timestamp": _ts(4, 8, 0),
            "request_headers": {"Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"status":"ok"}',
        },
        {
            "id": "a0000001-000c-4000-8000-00000000000c",
            "method": "DELETE",
            "url": "https://api.shop.example.com/v2/users/usr_old_999",
            "status": 204,
            "elapsed_ms": 67.8,
            "timestamp": _ts(3, 13, 40),
            "request_headers": {"X-API-Key": "sk_test_demo_key_12345"},
            "response_headers": {},
            "request_body": None,
            "response_body": "",
        },
        {
            "id": "a0000001-000d-4000-8000-00000000000d",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/products/ELEC-001",
            "status": 404,
            "elapsed_ms": 44.5,
            "timestamp": _ts(2, 16, 5),
            "request_headers": {"Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"error":"product_not_found","message":"Product ELEC-001 not found or discontinued"}',
        },
        {
            "id": "a0000001-000e-4000-8000-00000000000e",
            "method": "POST",
            "url": "https://api.shop.example.com/v2/orders",
            "status": 422,
            "elapsed_ms": 89.1,
            "timestamp": _ts(1, 10, 15),
            "request_headers": {"Content-Type": "application/json"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": '{"user_id":"usr_001","items":[]}',
            "response_body": '{"error":"validation_failed","message":"items must not be empty","field":"items"}',
        },
        {
            "id": "a0000001-000f-4000-8000-00000000000f",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/users?page=1&limit=20",
            "status": 200,
            "elapsed_ms": 91.6,
            "timestamp": _ts(0.1, 9, 0),
            "request_headers": {"Accept": "application/json", "X-API-Key": "sk_test_demo_key_12345"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"success":true,"data":[{"id":"usr_001","email":"alice@example.com"}],"total":41,"page":1}',
        },
    ]

    _atomic_jsonl_write(history_path, entries)
    logger.info("  Seeded %d history entries", len(entries))


# ---------------------------------------------------------------------------
# Load test results seed
# ---------------------------------------------------------------------------

def _seed_load_results(load_results_path: Path) -> None:
    """Write demo load test results if file is absent/empty."""
    if load_results_path.exists() and load_results_path.stat().st_size > 0:
        return

    logger.info("Seeding demo load test results…")

    def _timeline(duration_s: int, rps_base: float, lat_base: float, error_rate: float = 0.0) -> list[dict]:
        import math, random
        random.seed(42)
        pts = []
        for s in range(duration_s):
            # Simulate a ramp-up in the first 5 seconds
            ramp = min(1.0, (s + 1) / 5)
            rps = round(rps_base * ramp + random.gauss(0, rps_base * 0.05), 2)
            lat = round(lat_base * (1 + 0.1 * math.sin(s / 3)) + random.gauss(0, lat_base * 0.1), 2)
            errs = round(rps * error_rate, 4)
            pts.append({
                "second": s,
                "rps": max(0.0, rps),
                "avg_latency_ms": max(0.0, lat),
                "error_count": int(errs),
                "active_users": min(s + 1, 20),
                "error_rate": error_rate,
                "p95_ms": round(lat * 1.4, 2),
            })
        return pts

    results = [
        # Smoke test — fast, clean
        {
            "id": "b0000001-0001-4000-8000-000000000001",
            "url": "https://api.shop.example.com/v2/health",
            "method": "GET",
            "virtual_users": 5,
            "duration_seconds": 30,
            "ramp_up_seconds": 5,
            "started_at": _ts(14, 10, 0),
            "collection_name": "E-Commerce API",
            "label": "Smoke — Health Check",
            "total_requests": 1243,
            "successful": 1243,
            "failed": 0,
            "errors": {},
            "avg_latency_ms": 14.2,
            "min_latency_ms": 8.1,
            "max_latency_ms": 42.5,
            "p50_ms": 13.0,
            "p75_ms": 17.4,
            "p90_ms": 22.6,
            "p95_ms": 28.3,
            "p99_ms": 39.7,
            "requests_per_second": 41.43,
            "duration_seconds": 30.0,
            "timeline": _timeline(30, 41.0, 14.0),
        },
        # Baseline load — moderate traffic, slightly high p99
        {
            "id": "b0000001-0002-4000-8000-000000000002",
            "url": "https://api.shop.example.com/v2/products?category=electronics",
            "method": "GET",
            "virtual_users": 20,
            "duration_seconds": 60,
            "ramp_up_seconds": 10,
            "started_at": _ts(10, 14, 0),
            "collection_name": "E-Commerce API",
            "label": "Baseline — List Products",
            "total_requests": 7821,
            "successful": 7809,
            "failed": 12,
            "errors": {"ConnectionTimeout": 12},
            "avg_latency_ms": 68.7,
            "min_latency_ms": 31.2,
            "max_latency_ms": 1243.4,
            "p50_ms": 63.1,
            "p75_ms": 88.4,
            "p90_ms": 124.6,
            "p95_ms": 187.2,
            "p99_ms": 491.8,
            "requests_per_second": 130.35,
            "duration_seconds": 60.0,
            "timeline": _timeline(60, 130.0, 68.0, 0.002),
        },
        # Stress test — high VU, elevated errors
        {
            "id": "b0000001-0003-4000-8000-000000000003",
            "url": "https://api.shop.example.com/v2/orders",
            "method": "POST",
            "virtual_users": 100,
            "duration_seconds": 120,
            "ramp_up_seconds": 20,
            "started_at": _ts(5, 9, 0),
            "collection_name": "E-Commerce API",
            "label": "Stress — Place Order",
            "total_requests": 24_506,
            "successful": 22_891,
            "failed": 1615,
            "errors": {"ConnectError": 892, "ConnectionTimeout": 723},
            "avg_latency_ms": 342.1,
            "min_latency_ms": 45.3,
            "max_latency_ms": 9872.5,
            "p50_ms": 289.4,
            "p75_ms": 421.7,
            "p90_ms": 614.9,
            "p95_ms": 843.2,
            "p99_ms": 2341.7,
            "requests_per_second": 204.22,
            "duration_seconds": 120.0,
            "timeline": _timeline(120, 200.0, 340.0, 0.066),
        },
        # Soak test — 5 minutes, stable, finding memory issue
        {
            "id": "b0000001-0004-4000-8000-000000000004",
            "url": "https://api.shop.example.com/v2/users",
            "method": "GET",
            "virtual_users": 10,
            "duration_seconds": 300,
            "ramp_up_seconds": 15,
            "started_at": _ts(2, 11, 0),
            "collection_name": "E-Commerce API",
            "label": "Soak — List Users (5 min)",
            "total_requests": 87_432,
            "successful": 87_388,
            "failed": 44,
            "errors": {"ConnectionTimeout": 44},
            "avg_latency_ms": 34.1,
            "min_latency_ms": 9.8,
            "max_latency_ms": 782.3,
            "p50_ms": 30.5,
            "p75_ms": 44.2,
            "p90_ms": 62.8,
            "p95_ms": 84.1,
            "p99_ms": 214.6,
            "requests_per_second": 291.44,
            "duration_seconds": 300.0,
            "timeline": _timeline(300, 290.0, 34.0, 0.0005),
        },
    ]

    _atomic_jsonl_write(load_results_path, results)
    logger.info("  Seeded %d load test results", len(results))


# ---------------------------------------------------------------------------
# Security scan results seed
# ---------------------------------------------------------------------------

def _seed_security_scans(security_scans_path: Path) -> None:
    """Write demo security scan results if file is absent/empty."""
    if security_scans_path.exists() and security_scans_path.stat().st_size > 0:
        return

    logger.info("Seeding demo security scan results…")

    scans = [
        # Clean scan — no findings
        {
            "id": "c0000001-0001-4000-8000-000000000001",
            "url": "https://api.shop.example.com/v2/health",
            "method": "GET",
            "scan_types_run": ["sql_injection", "xss", "auth_bypass", "rate_limit"],
            "score": 98,
            "elapsed_ms": 1243.7,
            "started_at": _ts(13, 15, 0),
            "collection_name": "E-Commerce API",
            "findings": [],
        },
        # Medium-risk scan — one info finding, one medium
        {
            "id": "c0000001-0002-4000-8000-000000000002",
            "url": "https://api.shop.example.com/v2/products",
            "method": "GET",
            "scan_types_run": ["sql_injection", "xss"],
            "score": 74,
            "elapsed_ms": 3412.5,
            "started_at": _ts(9, 14, 30),
            "collection_name": "E-Commerce API",
            "findings": [
                {
                    "scan_type": "xss",
                    "severity": "medium",
                    "title": "Reflected Parameter in Error Response",
                    "evidence": "GET /v2/products?category=<script>alert(1)</script> → 400: invalid category: <script>…",
                    "description": (
                        "The 'category' query parameter value is reflected back in the 400 error response "
                        "body without HTML-encoding. An attacker could craft a link that causes a script "
                        "injection in victim's browser. Apply output encoding for all user-supplied values "
                        "in error messages."
                    ),
                },
                {
                    "scan_type": "sql_injection",
                    "severity": "info",
                    "title": "SQL Error Strings Suppressed",
                    "evidence": "No SQL dialect errors found in responses for 5 injection payloads.",
                    "description": (
                        "The endpoint appears to suppress SQL error messages, which is good practice. "
                        "Ensure error handling is consistent across all environments (dev/staging/prod)."
                    ),
                },
            ],
        },
        # High-risk scan — critical SQL injection found
        {
            "id": "c0000001-0003-4000-8000-000000000003",
            "url": "https://api.shop.example.com/v2/users",
            "method": "GET",
            "scan_types_run": ["sql_injection", "xss", "auth_bypass", "rate_limit"],
            "score": 32,
            "elapsed_ms": 8741.2,
            "started_at": _ts(6, 10, 0),
            "collection_name": "E-Commerce API",
            "findings": [
                {
                    "scan_type": "sql_injection",
                    "severity": "critical",
                    "title": "SQL Injection via 'search' Parameter",
                    "evidence": (
                        "GET /v2/users?search=' OR '1'='1 → 200 OK, returns all users. "
                        "Response contained 'mysql_query error' in debug header."
                    ),
                    "description": (
                        "The 'search' query parameter is directly interpolated into a SQL query without "
                        "parameterization. An attacker can enumerate all users or execute arbitrary SQL. "
                        "Fix: use parameterized queries or an ORM; never interpolate user input into SQL."
                    ),
                },
                {
                    "scan_type": "auth_bypass",
                    "severity": "high",
                    "title": "Missing Authorization on User List Endpoint",
                    "evidence": (
                        "GET /v2/users without Authorization header → 200 OK with full user list."
                    ),
                    "description": (
                        "The /v2/users endpoint returns the full user list without requiring authentication. "
                        "This exposes PII (email, role, last_login) to unauthenticated callers. "
                        "Enforce authentication middleware for all /v2/users routes."
                    ),
                },
                {
                    "scan_type": "rate_limit",
                    "severity": "medium",
                    "title": "No Rate Limiting on User Enumeration",
                    "evidence": "20 rapid requests to /v2/users returned 200 each; no 429 observed.",
                    "description": (
                        "The endpoint does not enforce rate limiting. Combined with the auth bypass finding, "
                        "this enables rapid data exfiltration. Implement rate limiting (e.g. 60 req/min per IP)."
                    ),
                },
                {
                    "scan_type": "xss",
                    "severity": "low",
                    "title": "Missing Content-Security-Policy Header",
                    "evidence": "Response headers: no Content-Security-Policy header found.",
                    "description": (
                        "The API does not set a Content-Security-Policy header. While less critical for pure APIs, "
                        "adding a restrictive CSP reduces the attack surface for any HTML error pages."
                    ),
                },
            ],
        },
        # Recent clean scan
        {
            "id": "c0000001-0004-4000-8000-000000000004",
            "url": "https://api.shop.example.com/v2/health",
            "method": "GET",
            "scan_types_run": ["sql_injection", "xss", "auth_bypass"],
            "score": 100,
            "elapsed_ms": 987.3,
            "started_at": _ts(1, 16, 0),
            "collection_name": "E-Commerce API",
            "findings": [],
        },
    ]

    _atomic_jsonl_write(security_scans_path, scans)
    logger.info("  Seeded %d security scans", len(scans))


# ---------------------------------------------------------------------------
# Atomic write helpers
# ---------------------------------------------------------------------------

def _atomic_json_write(path: Path, data: Any) -> None:
    """Write *data* as JSON to *path* atomically (temp-then-rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=f"{path.stem}.", suffix=".tmp", dir=str(path.parent),
    )
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _atomic_jsonl_write(path: Path, rows: list[dict]) -> None:
    """Write *rows* as JSONL to *path* atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=f"{path.stem}.", suffix=".tmp", dir=str(path.parent),
    )
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def seed_all(home: Path) -> None:
    """Seed all data stores under *home* if they are empty (idempotent)."""
    try:
        _seed_collections(home / "collections")
        _seed_history(home / "history.jsonl")
        _seed_load_results(home / "load_results.jsonl")
        _seed_security_scans(home / "security_scans.jsonl")
    except Exception:
        logger.exception("Seed failed (non-fatal — continuing without demo data)")
