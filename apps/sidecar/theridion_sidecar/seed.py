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
# Fixed UUIDs for newly-seeded entities
# ---------------------------------------------------------------------------

# Environments
_ENV_PRODUCTION_ID  = "e1111111-0001-4000-8000-000000000001"
_ENV_STAGING_ID     = "e1111111-0002-4000-8000-000000000002"
_ENV_LOCAL_ID       = "e1111111-0003-4000-8000-000000000003"
_ENV_GRAPHQL_ID     = "e1111111-0004-4000-8000-000000000004"

# Monitors (reference real collection ids and env ids defined above)
_MON_HEALTH_ID      = "d2222222-0001-4000-8000-000000000001"
_MON_USERS_ID       = "d2222222-0002-4000-8000-000000000002"
_MON_ORDERS_ID      = "d2222222-0003-4000-8000-000000000003"

# Snippets
_SNIP_AUTH_BEARER_ID = "snip0001-0001-4000-8000-000000000001"
_SNIP_JSON_POST_ID   = "snip0001-0002-4000-8000-000000000002"
_SNIP_PAGINATION_ID  = "snip0001-0003-4000-8000-000000000003"
_SNIP_GRAPHQL_ID     = "snip0001-0004-4000-8000-000000000004"

# Mock recording session
_MOCK_SESSION_ID    = "mock-session-demo-001"


# ---------------------------------------------------------------------------
# Environments seed
# ---------------------------------------------------------------------------

def _seed_environments(envs_dir: Path) -> None:
    """Write demo environments if the directory is empty."""
    existing = list(envs_dir.glob("*.json"))
    if existing:
        return

    logger.info("Seeding demo environments…")

    environments = [
        {
            "id": _ENV_PRODUCTION_ID,
            "name": "Production",
            "variables": [
                {"name": "base_url", "value": "https://api.shop.example.com/v2", "enabled": True},
                {"name": "api_key", "value": "sk_live_demo_key_PROD_99999", "enabled": True},
                {"name": "timeout_ms", "value": "5000", "enabled": True},
                {"name": "log_level", "value": "error", "enabled": True},
                {"name": "cdn_url", "value": "https://cdn.shop.example.com", "enabled": True},
            ],
        },
        {
            "id": _ENV_STAGING_ID,
            "name": "Staging",
            "variables": [
                {"name": "base_url", "value": "https://api-staging.shop.example.com/v2", "enabled": True},
                {"name": "api_key", "value": "sk_staging_demo_key_12345", "enabled": True},
                {"name": "timeout_ms", "value": "10000", "enabled": True},
                {"name": "log_level", "value": "info", "enabled": True},
                {"name": "cdn_url", "value": "https://cdn-staging.shop.example.com", "enabled": True},
                {"name": "mock_payments", "value": "true", "enabled": True},
            ],
        },
        {
            "id": _ENV_LOCAL_ID,
            "name": "Local Dev",
            "variables": [
                {"name": "base_url", "value": "http://localhost:3000/v2", "enabled": True},
                {"name": "api_key", "value": "sk_test_demo_key_12345", "enabled": True},
                {"name": "timeout_ms", "value": "30000", "enabled": True},
                {"name": "log_level", "value": "debug", "enabled": True},
                {"name": "cdn_url", "value": "http://localhost:3001", "enabled": True},
                {"name": "mock_payments", "value": "true", "enabled": True},
                {"name": "debug_mode", "value": "true", "enabled": True},
            ],
        },
        {
            "id": _ENV_GRAPHQL_ID,
            "name": "GitHub GraphQL",
            "variables": [
                {"name": "endpoint", "value": "https://api.github.com/graphql", "enabled": True},
                {"name": "token", "value": "ghp_demo_token_replace_me", "enabled": True},
                {"name": "viewer_login", "value": "alice-dev", "enabled": True},
            ],
        },
    ]

    envs_dir.mkdir(parents=True, exist_ok=True)
    for env_data in environments:
        env_path = envs_dir / f"{env_data['id']}.json"
        _atomic_json_write(env_path, env_data)
        logger.info("  Seeded environment: %s (%s)", env_data["name"], env_data["id"])


# ---------------------------------------------------------------------------
# Global variables seed
# ---------------------------------------------------------------------------

def _seed_globals(globals_path: Path) -> None:
    """Write demo global variables if the file does not exist."""
    if globals_path.exists() and globals_path.stat().st_size > 0:
        return

    logger.info("Seeding demo global variables…")

    store = {
        "variables": [
            {"name": "app_name", "value": "Theridion Net Demo", "enabled": True},
            {"name": "demo_user_id", "value": "usr_001", "enabled": True},
            {"name": "auth_url", "value": "https://auth.shop.example.com", "enabled": True},
            {"name": "client_id", "value": "client_demo_theridion", "enabled": True},
            {"name": "client_secret", "value": "secret_demo_replace_in_prod", "enabled": True},
            {"name": "webhook_url", "value": "https://hooks.example.com/theridion", "enabled": True},
            {"name": "tracing_header", "value": "X-Request-Id", "enabled": True},
            # Disabled example showing how to override per-run
            {"name": "debug_override", "value": "false", "enabled": False},
        ],
    }
    _atomic_json_write(globals_path, store)
    logger.info("  Seeded %d global variables", len(store["variables"]))


# ---------------------------------------------------------------------------
# User snippets seed
# ---------------------------------------------------------------------------

def _seed_snippets(snippets_dir: Path) -> None:
    """Write demo user snippets if the directory is empty."""
    existing = list(snippets_dir.glob("*.json"))
    if existing:
        return

    logger.info("Seeding demo user snippets…")

    now = _ts(0)
    snippets = [
        {
            "id": _SNIP_AUTH_BEARER_ID,
            "name": "Bearer Token Auth Header",
            "category": "Auth",
            "description": "Adds Authorization Bearer header from environment variable",
            "method": "GET",
            "url": "{{base_url}}/me",
            "headers": {"Authorization": "Bearer {{api_key}}", "Accept": "application/json"},
            "body": None,
            "auth": None,
            "tags": ["auth", "bearer", "jwt"],
            "created_at": _ts(30),
            "updated_at": _ts(5),
            "builtin": False,
        },
        {
            "id": _SNIP_JSON_POST_ID,
            "name": "JSON POST with CSRF",
            "category": "Common",
            "description": "POST request with JSON body and CSRF token header",
            "method": "POST",
            "url": "{{base_url}}/resources",
            "headers": {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-CSRF-Token": "{{csrf_token}}",
                "Authorization": "Bearer {{api_key}}",
            },
            "body": json.dumps({"name": "example", "type": "demo", "active": True}, indent=2),
            "auth": None,
            "tags": ["post", "json", "csrf"],
            "created_at": _ts(25),
            "updated_at": _ts(3),
            "builtin": False,
        },
        {
            "id": _SNIP_PAGINATION_ID,
            "name": "Paginated List Request",
            "category": "Common",
            "description": "GET request with cursor-based pagination parameters",
            "method": "GET",
            "url": "{{base_url}}/items?limit=20&cursor={{cursor}}&sort=created_at&order=desc",
            "headers": {"Accept": "application/json", "X-API-Key": "{{api_key}}"},
            "body": None,
            "auth": None,
            "tags": ["pagination", "list", "cursor"],
            "created_at": _ts(20),
            "updated_at": _ts(7),
            "builtin": False,
        },
        {
            "id": _SNIP_GRAPHQL_ID,
            "name": "GraphQL Mutation Template",
            "category": "GraphQL",
            "description": "Mutation template with variables and error handling",
            "method": "POST",
            "url": "{{endpoint}}",
            "headers": {
                "Content-Type": "application/json",
                "Authorization": "bearer {{token}}",
            },
            "body": json.dumps({
                "query": "mutation ($input: CreateResourceInput!) { createResource(input: $input) { id status errors { field message } } }",
                "variables": {"input": {"name": "Demo", "type": "test"}},
            }, indent=2),
            "auth": None,
            "tags": ["graphql", "mutation", "template"],
            "created_at": _ts(15),
            "updated_at": _ts(2),
            "builtin": False,
        },
    ]

    snippets_dir.mkdir(parents=True, exist_ok=True)
    for snip in snippets:
        snip_path = snippets_dir / f"{snip['id']}.json"
        _atomic_json_write(snip_path, snip)
        logger.info("  Seeded snippet: %s", snip["name"])


# ---------------------------------------------------------------------------
# Monitors seed
# ---------------------------------------------------------------------------

def _seed_monitors(monitors_path: Path) -> None:
    """Write demo monitors if the file does not exist."""
    if monitors_path.exists() and monitors_path.stat().st_size > 0:
        return

    logger.info("Seeding demo monitors…")

    monitors = [
        {
            "id": _MON_HEALTH_ID,
            "collection_id": _COL_REST_ID,
            "environment_id": _ENV_PRODUCTION_ID,
            "cron": "*/5 * * * *",
            "enabled": True,
            "last_run": None,
            "last_status": None,
        },
        {
            "id": _MON_USERS_ID,
            "collection_id": _COL_REST_ID,
            "environment_id": _ENV_STAGING_ID,
            "cron": "0 * * * *",
            "enabled": True,
            "last_run": None,
            "last_status": None,
        },
        {
            "id": _MON_ORDERS_ID,
            "collection_id": _COL_SOAP_ID,
            "environment_id": _ENV_STAGING_ID,
            "cron": "0 6 * * *",
            "enabled": False,
            "last_run": None,
            "last_status": None,
        },
    ]

    monitors_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json_write(monitors_path, monitors)
    logger.info("  Seeded %d monitors", len(monitors))


# ---------------------------------------------------------------------------
# Service map seed
# ---------------------------------------------------------------------------

def _seed_servicemap(servicemap_path: Path) -> None:
    """Write a demo service dependency graph if the file does not exist."""
    if servicemap_path.exists() and servicemap_path.stat().st_size > 0:
        return

    logger.info("Seeding demo service map…")

    # Node IDs
    n_api    = "sm-node-0001-4000-8000-000000000001"
    n_auth   = "sm-node-0002-4000-8000-000000000002"
    n_db     = "sm-node-0003-4000-8000-000000000003"
    n_cache  = "sm-node-0004-4000-8000-000000000004"
    n_pay    = "sm-node-0005-4000-8000-000000000005"
    n_cdn    = "sm-node-0006-4000-8000-000000000006"
    n_notify = "sm-node-0007-4000-8000-000000000007"

    graph = {
        "nodes": [
            {"id": n_api,    "label": "E-Commerce API",      "url": "https://api.shop.example.com",        "x": 300, "y": 200, "color": "#06b6d4"},
            {"id": n_auth,   "label": "Auth Service",         "url": "https://auth.shop.example.com",       "x": 100, "y": 100, "color": "#8b5cf6"},
            {"id": n_db,     "label": "PostgreSQL",           "url": "postgresql://db.shop.example.com",    "x": 100, "y": 350, "color": "#10b981"},
            {"id": n_cache,  "label": "Redis Cache",          "url": "redis://cache.shop.example.com",      "x": 500, "y": 100, "color": "#f59e0b"},
            {"id": n_pay,    "label": "Payment Gateway",      "url": "https://payments.example.com",        "x": 500, "y": 350, "color": "#ef4444"},
            {"id": n_cdn,    "label": "CDN",                  "url": "https://cdn.shop.example.com",        "x": 300, "y": 450, "color": "#ec4899"},
            {"id": n_notify, "label": "Notification Service", "url": "https://notify.shop.example.com",     "x": 700, "y": 200, "color": "#6366f1"},
        ],
        "edges": [
            {"id": "sm-edge-001", "source": n_api,  "target": n_auth,   "label": "validates token"},
            {"id": "sm-edge-002", "source": n_api,  "target": n_db,     "label": "read/write"},
            {"id": "sm-edge-003", "source": n_api,  "target": n_cache,  "label": "session cache"},
            {"id": "sm-edge-004", "source": n_api,  "target": n_pay,    "label": "charge card"},
            {"id": "sm-edge-005", "source": n_api,  "target": n_cdn,    "label": "serve assets"},
            {"id": "sm-edge-006", "source": n_api,  "target": n_notify, "label": "order events"},
            {"id": "sm-edge-007", "source": n_pay,  "target": n_notify, "label": "payment events"},
        ],
    }

    servicemap_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json_write(servicemap_path, graph)
    logger.info("  Seeded service map (%d nodes, %d edges)",
                len(graph["nodes"]), len(graph["edges"]))


# ---------------------------------------------------------------------------
# Performance budgets + violations seed
# ---------------------------------------------------------------------------

def _seed_perf_budgets(budgets_path: Path, violations_path: Path) -> None:
    """Write demo performance budgets and violations if files are absent/empty."""
    if budgets_path.exists() and budgets_path.stat().st_size > 0:
        return

    logger.info("Seeding demo performance budgets…")

    budgets = [
        {
            "id": "pbud0001",
            "url_pattern": "https://api.shop.example.com/v2/health",
            "method": "GET",
            "max_time_ms": 100,
            "max_size_bytes": 4096,
            "p95_time_ms": 80,
            "alert_threshold": 3,
            "name": "Health Check — critical path",
        },
        {
            "id": "pbud0002",
            "url_pattern": "https://api.shop.example.com/v2/products*",
            "method": "GET",
            "max_time_ms": 250,
            "max_size_bytes": 102400,
            "p95_time_ms": 200,
            "alert_threshold": 5,
            "name": "Product List — catalogue API",
        },
        {
            "id": "pbud0003",
            "url_pattern": "https://api.shop.example.com/v2/orders",
            "method": "POST",
            "max_time_ms": 500,
            "max_size_bytes": None,
            "p95_time_ms": 400,
            "alert_threshold": 3,
            "name": "Place Order — checkout critical",
        },
        {
            "id": "pbud0004",
            "url_pattern": "https://api.shop.example.com/v2/users*",
            "method": None,
            "max_time_ms": 200,
            "max_size_bytes": 51200,
            "p95_time_ms": 150,
            "alert_threshold": 5,
            "name": "User API — all methods",
        },
    ]

    budgets_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json_write(budgets_path, budgets)
    logger.info("  Seeded %d performance budgets", len(budgets))

    if violations_path.exists() and violations_path.stat().st_size > 0:
        return

    logger.info("Seeding demo performance violations…")

    violations = [
        {
            "budget_id": "pbud0003",
            "budget_name": "Place Order — checkout critical",
            "metric": "max_time_ms",
            "actual": 843.2,
            "threshold": 500.0,
            "exceeded_by_percent": 68.6,
            "url": "https://api.shop.example.com/v2/orders",
            "method": "POST",
            "timestamp": _ts(5, 9, 0),
        },
        {
            "budget_id": "pbud0004",
            "budget_name": "User API — all methods",
            "metric": "p95_time_ms",
            "actual": 214.6,
            "threshold": 150.0,
            "exceeded_by_percent": 43.1,
            "url": "https://api.shop.example.com/v2/users",
            "method": "GET",
            "timestamp": _ts(2, 11, 0),
        },
        {
            "budget_id": "pbud0002",
            "budget_name": "Product List — catalogue API",
            "metric": "max_time_ms",
            "actual": 491.8,
            "threshold": 250.0,
            "exceeded_by_percent": 96.7,
            "url": "https://api.shop.example.com/v2/products?category=electronics",
            "method": "GET",
            "timestamp": _ts(10, 14, 0),
        },
    ]

    _atomic_json_write(violations_path, violations)
    logger.info("  Seeded %d performance violations", len(violations))


# ---------------------------------------------------------------------------
# Mock recordings seed
# ---------------------------------------------------------------------------

def _seed_mock_recordings(recordings_dir: Path) -> None:
    """Write a demo mock recording session if the directory is empty."""
    existing = list(recordings_dir.glob("*.json"))
    if existing:
        return

    logger.info("Seeding demo mock recording…")

    recording = {
        "session_id": _MOCK_SESSION_ID,
        "target_url": "https://api.shop.example.com",
        "recorded_at": _ts(7, 10, 0),
        "interactions": [
            {
                "method": "GET",
                "path": "/v2/health",
                "query": "",
                "request_headers": {"Accept": "application/json"},
                "request_body": None,
                "status": 200,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": json.dumps({"status": "ok", "version": "2.4.1"}),
                "elapsed_ms": 14.2,
                "timestamp": _ts(7, 10, 0),
            },
            {
                "method": "GET",
                "path": "/v2/users",
                "query": "page=1&limit=20",
                "request_headers": {"Accept": "application/json", "X-API-Key": "sk_test_demo_key_12345"},
                "request_body": None,
                "status": 200,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": json.dumps({
                    "success": True,
                    "data": [
                        {"id": "usr_001", "email": "alice@example.com", "role": "customer"},
                        {"id": "usr_002", "email": "bob@example.com", "role": "admin"},
                    ],
                    "total": 2,
                    "page": 1,
                }),
                "elapsed_ms": 87.3,
                "timestamp": _ts(7, 10, 1),
            },
            {
                "method": "GET",
                "path": "/v2/products",
                "query": "category=electronics&in_stock=true",
                "request_headers": {"Accept": "application/json"},
                "request_body": None,
                "status": 200,
                "response_headers": {"Content-Type": "application/json", "Cache-Control": "max-age=60"},
                "response_body": json.dumps({
                    "success": True,
                    "data": [{"sku": "ELEC-001", "name": "Wireless Mouse", "price": 49.99, "stock": 234}],
                    "total": 1,
                }),
                "elapsed_ms": 62.1,
                "timestamp": _ts(7, 10, 2),
            },
            {
                "method": "POST",
                "path": "/v2/orders",
                "query": "",
                "request_headers": {"Content-Type": "application/json", "Authorization": "Bearer sk_test_demo_key_12345"},
                "request_body": json.dumps({"user_id": "usr_001", "items": [{"sku": "ELEC-001", "qty": 1, "unit_price": 49.99}]}),
                "status": 201,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": json.dumps({"order_id": "ord_demo_001", "status": "pending", "total": 49.99}),
                "elapsed_ms": 142.8,
                "timestamp": _ts(7, 10, 3),
            },
        ],
    }

    recordings_dir.mkdir(parents=True, exist_ok=True)
    rec_path = recordings_dir / f"{_MOCK_SESSION_ID}.json"
    _atomic_json_write(rec_path, recording)
    logger.info("  Seeded mock recording: %s (%d interactions)",
                _MOCK_SESSION_ID, len(recording["interactions"]))


# ---------------------------------------------------------------------------
# Interceptor flows seed  (in-process state — injected at startup)
# ---------------------------------------------------------------------------

def _seed_interceptor_flows() -> None:
    """Inject demo captured flows into the interceptor's in-memory registry.

    The interceptor uses a module-level dict ``_flows`` — we inject entries
    only when that dict is empty so real flows are never clobbered.
    """
    try:
        from theridion_sidecar.api import interceptor as _ic
        if _ic._flows:
            return

        logger.info("Seeding demo interceptor flows…")

        demo_flows_data = [
            {
                "flow_id": "flow-demo-0001-4000-8000-000000000001",
                "timestamp": _ts(0.5, 9, 0),
                "method": "GET",
                "url": "https://api.shop.example.com/v2/users?page=1&limit=20",
                "request_headers": {"Accept": "application/json", "X-API-Key": "sk_test_demo_key_12345"},
                "request_body": None,
                "status_code": 200,
                "response_headers": {"Content-Type": "application/json", "X-Request-Id": "req_abc001"},
                "response_body": '{"success":true,"data":[{"id":"usr_001","email":"alice@example.com"}],"total":42}',
                "elapsed_ms": 91.6,
                "state": "forwarded",
                "flags": [],
                "error": None,
            },
            {
                "flow_id": "flow-demo-0002-4000-8000-000000000002",
                "timestamp": _ts(0.4, 9, 5),
                "method": "POST",
                "url": "https://api.shop.example.com/v2/orders",
                "request_headers": {"Content-Type": "application/json", "Authorization": "Bearer sk_test_demo_key_12345"},
                "request_body": '{"user_id":"usr_001","items":[{"sku":"ELEC-001","qty":1,"unit_price":49.99}]}',
                "status_code": 201,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": '{"order_id":"ord_demo_001","status":"pending","total":49.99}',
                "elapsed_ms": 142.8,
                "state": "forwarded",
                "flags": [
                    {
                        "type": "missing_header",
                        "severity": "medium",
                        "location": "response_headers",
                        "detail": "Missing Content-Security-Policy header",
                    },
                    {
                        "type": "missing_header",
                        "severity": "low",
                        "location": "response_headers",
                        "detail": "Missing X-Content-Type-Options header",
                    },
                ],
                "error": None,
            },
            {
                "flow_id": "flow-demo-0003-4000-8000-000000000003",
                "timestamp": _ts(0.3, 9, 10),
                "method": "GET",
                "url": "https://api.shop.example.com/v2/products/ELEC-999",
                "request_headers": {"Accept": "application/json"},
                "request_body": None,
                "status_code": 404,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": '{"error":"product_not_found","message":"Product ELEC-999 not found"}',
                "elapsed_ms": 44.5,
                "state": "forwarded",
                "flags": [
                    {
                        "type": "missing_header",
                        "severity": "medium",
                        "location": "response_headers",
                        "detail": "Missing Content-Security-Policy header",
                    },
                ],
                "error": None,
            },
            {
                "flow_id": "flow-demo-0004-4000-8000-000000000004",
                "timestamp": _ts(0.1, 10, 0),
                "method": "DELETE",
                "url": "https://api.shop.example.com/v2/users/usr_old_999",
                "request_headers": {"X-API-Key": "sk_test_demo_key_12345"},
                "request_body": None,
                "status_code": 204,
                "response_headers": {},
                "response_body": "",
                "elapsed_ms": 67.8,
                "state": "forwarded",
                "flags": [],
                "error": None,
            },
        ]

        for flow_data in demo_flows_data:
            flow = _ic.CapturedFlow(**flow_data)
            _ic._flows[flow.flow_id] = flow

        logger.info("  Seeded %d interceptor flows", len(demo_flows_data))
    except Exception:
        logger.debug("Could not seed interceptor flows (non-fatal)", exc_info=True)


# ---------------------------------------------------------------------------
# Webhooks seed
# ---------------------------------------------------------------------------

def _seed_webhooks(webhooks_path: Path) -> None:
    """Write demo webhooks if the file does not exist."""
    if webhooks_path.exists() and webhooks_path.stat().st_size > 0:
        return

    logger.info("Seeding demo webhooks…")

    webhooks = [
        {
            "id": "wh000001",
            "collection_id": _COL_REST_ID,
            "environment_id": _ENV_STAGING_ID,
            "url": "https://hooks.example.com/theridion/ci-trigger",
            "enabled": True,
        },
        {
            "id": "wh000002",
            "collection_id": _COL_GRAPHQL_ID,
            "environment_id": _ENV_LOCAL_ID,
            "url": "https://hooks.example.com/theridion/graphql-smoke",
            "enabled": False,
        },
    ]

    webhooks_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json_write(webhooks_path, webhooks)
    logger.info("  Seeded %d webhooks", len(webhooks))


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
        _seed_environments(home / "environments")
        _seed_globals(home / "globals.json")
        _seed_snippets(home / "snippets")
        _seed_monitors(home / "monitors.json")
        _seed_servicemap(home / "servicemap.json")
        _seed_perf_budgets(home / "perf_budgets.json", home / "perf_violations.json")
        _seed_mock_recordings(home / "mock_recordings")
        _seed_interceptor_flows()
        _seed_webhooks(home / "webhooks.json")
    except Exception:
        logger.exception("Seed failed (non-fatal — continuing without demo data)")
