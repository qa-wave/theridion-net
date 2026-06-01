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
_COL_WS_ID = "a1b2c3d4-0005-4000-8000-000000000005"

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
_REQ_GET_ORDER = "b1000001-000b-4000-8000-000000000011"
_REQ_CANCEL_ORDER = "b1000001-000c-4000-8000-000000000012"
_REQ_SEARCH_PRODUCTS = "b1000001-000d-4000-8000-000000000013"
_REQ_GET_COUPONS = "b1000001-000e-4000-8000-000000000014"
_REQ_AUTH_LOGIN = "b1000001-000f-4000-8000-000000000015"
_REQ_AUTH_REFRESH = "b1000001-0010-4000-8000-000000000016"

# Folder ids
_FOLDER_USERS = "f1000001-0001-4000-8000-000000000001"
_FOLDER_PRODUCTS = "f1000001-0002-4000-8000-000000000002"
_FOLDER_ORDERS = "f1000001-0003-4000-8000-000000000003"
_FOLDER_AUTH = "f1000001-0004-4000-8000-000000000004"
_FOLDER_PROMOTIONS = "f1000001-0005-4000-8000-000000000005"


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
                            {"type": "response_time", "expected": "1000", "path": "", "operator": "lt"},
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
                            {"type": "json_path", "expected": "", "path": "data", "operator": "exists"},
                        ],
                        "captures": [],
                        "tags": ["orders"],
                        "examples": [],
                        "notes": None,
                        "items": [],
                    },
                    {
                        "id": _REQ_GET_ORDER,
                        "name": "Get Order Detail",
                        "is_folder": False,
                        "kind": "request",
                        "method": "GET",
                        "url": "{{base_url}}/orders/{{order_id}}",
                        "headers": {
                            "Accept": "application/json",
                            "Authorization": "Bearer {{api_key}}",
                        },
                        "body": None,
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                            {"type": "json_path", "expected": "", "path": "order_id", "operator": "exists"},
                            {"type": "json_path", "expected": "", "path": "items", "operator": "exists"},
                        ],
                        "captures": [],
                        "tags": ["orders"],
                        "examples": [],
                        "notes": "Fetches full order including line items and shipping status.",
                        "items": [],
                    },
                    {
                        "id": _REQ_CANCEL_ORDER,
                        "name": "Cancel Order",
                        "is_folder": False,
                        "kind": "request",
                        "method": "DELETE",
                        "url": "{{base_url}}/orders/{{order_id}}",
                        "headers": {
                            "Authorization": "Bearer {{api_key}}",
                        },
                        "body": None,
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "204", "path": "", "operator": "eq"},
                        ],
                        "captures": [],
                        "tags": ["orders", "cancel"],
                        "examples": [],
                        "notes": "Cancels an order if it has not yet shipped.",
                        "items": [],
                    },
                ],
            },
            {
                "id": _FOLDER_AUTH,
                "name": "Auth",
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
                "notes": "Authentication flow — obtain and refresh JWT tokens",
                "items": [
                    {
                        "id": _REQ_AUTH_LOGIN,
                        "name": "Login",
                        "is_folder": False,
                        "kind": "request",
                        "method": "POST",
                        "url": "{{base_url}}/auth/login",
                        "headers": {"Content-Type": "application/json"},
                        "body": json.dumps({"email": "alice@example.com", "password": "demo_pass_123"}, indent=2),
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                            {"type": "json_path", "expected": "", "path": "access_token", "operator": "exists"},
                            {"type": "json_path", "expected": "", "path": "refresh_token", "operator": "exists"},
                        ],
                        "captures": [
                            {"name": "access_token", "source": "body", "path": "access_token"},
                            {"name": "refresh_token", "source": "body", "path": "refresh_token"},
                        ],
                        "tags": ["auth", "login"],
                        "examples": [],
                        "notes": "Returns a short-lived JWT and long-lived refresh token.",
                        "items": [],
                    },
                    {
                        "id": _REQ_AUTH_REFRESH,
                        "name": "Refresh Token",
                        "is_folder": False,
                        "kind": "request",
                        "method": "POST",
                        "url": "{{base_url}}/auth/refresh",
                        "headers": {"Content-Type": "application/json"},
                        "body": json.dumps({"refresh_token": "{{refresh_token}}"}, indent=2),
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                            {"type": "json_path", "expected": "", "path": "access_token", "operator": "exists"},
                        ],
                        "captures": [
                            {"name": "access_token", "source": "body", "path": "access_token"},
                        ],
                        "tags": ["auth", "refresh"],
                        "examples": [],
                        "notes": "Exchange a refresh token for a new access token.",
                        "items": [],
                    },
                ],
            },
            {
                "id": _FOLDER_PROMOTIONS,
                "name": "Promotions",
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
                "notes": "Coupons and promotional discount endpoints",
                "items": [
                    {
                        "id": _REQ_SEARCH_PRODUCTS,
                        "name": "Search Products",
                        "is_folder": False,
                        "kind": "request",
                        "method": "GET",
                        "url": "{{base_url}}/products/search?q={{query}}&limit=20&sort=relevance",
                        "headers": {"Accept": "application/json"},
                        "body": None,
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                            {"type": "json_path", "expected": "", "path": "results", "operator": "exists"},
                            {"type": "response_time", "expected": "300", "path": "", "operator": "lt"},
                        ],
                        "captures": [],
                        "tags": ["products", "search"],
                        "examples": [],
                        "notes": "Full-text product search with relevance ranking.",
                        "items": [],
                    },
                    {
                        "id": _REQ_GET_COUPONS,
                        "name": "List Active Coupons",
                        "is_folder": False,
                        "kind": "request",
                        "method": "GET",
                        "url": "{{base_url}}/promotions/coupons?active=true",
                        "headers": {
                            "Accept": "application/json",
                            "Authorization": "Bearer {{access_token}}",
                        },
                        "body": None,
                        "auth": {"type": "none"},
                        "assertions": [
                            {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                            {"type": "json_path", "expected": "", "path": "coupons", "operator": "exists"},
                        ],
                        "captures": [],
                        "tags": ["promotions", "coupons"],
                        "examples": [],
                        "notes": "Returns currently active coupon codes with discount details.",
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
            {
                "id": str(uuid.UUID("c1000002-0004-4000-8000-000000000004")),
                "name": "Search Repositories",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{endpoint}}",
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "bearer {{token}}",
                },
                "body": json.dumps({
                    "query": """query SearchRepos($q: String!, $first: Int!) {
  search(query: $q, type: REPOSITORY, first: $first) {
    repositoryCount
    nodes { ... on Repository { name stargazerCount forkCount updatedAt } }
  }
}""",
                    "variables": {"q": "language:typescript stars:>1000", "first": 10},
                }, indent=2),
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                    {"type": "json_path", "expected": "", "path": "data.search.repositoryCount", "operator": "exists"},
                ],
                "captures": [],
                "tags": ["graphql", "search"],
                "examples": [],
                "notes": "Full-text repo search via GitHub GraphQL.",
                "items": [],
            },
            {
                "id": str(uuid.UUID("c1000002-0005-4000-8000-000000000005")),
                "name": "Get Pull Request Reviews",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{endpoint}}",
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "bearer {{token}}",
                },
                "body": json.dumps({
                    "query": """query PRReviews($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      title state reviews(first: 20) {
        nodes { author { login } state body submittedAt }
      }
    }
  }
}""",
                    "variables": {"owner": "alice-dev", "repo": "theridion", "number": 42},
                }, indent=2),
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                    {"type": "json_path", "expected": "", "path": "data.repository.pullRequest", "operator": "exists"},
                ],
                "captures": [],
                "tags": ["graphql", "pull-request"],
                "examples": [],
                "notes": "Fetch all review decisions for a specific PR.",
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
            {
                "id": str(uuid.UUID("d1000003-0004-4000-8000-000000000004")),
                "name": "DeleteUser RPC",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{grpc_host}}",
                "headers": {"content-type": "application/grpc+json"},
                "body": json.dumps({
                    "_grpc_method": "user.UserService/DeleteUser",
                    "user_id": "usr_7f4a1b2c",
                    "hard_delete": False,
                }),
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                    {"type": "json_path", "expected": "true", "path": "deleted", "operator": "eq"},
                ],
                "captures": [],
                "tags": ["grpc", "users", "delete"],
                "examples": [],
                "notes": "Soft-deletes a user. Set hard_delete=true to permanently purge.",
                "items": [],
            },
            {
                "id": str(uuid.UUID("d1000003-0005-4000-8000-000000000005")),
                "name": "StreamUserEvents (Server-Streaming)",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{grpc_host}}",
                "headers": {"content-type": "application/grpc+json"},
                "body": json.dumps({
                    "_grpc_method": "user.UserService/StreamUserEvents",
                    "user_id": "usr_7f4a1b2c",
                    "event_types": ["login", "profile_update", "order_placed"],
                }),
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                ],
                "captures": [],
                "tags": ["grpc", "streaming", "events"],
                "examples": [],
                "notes": "Server-streaming RPC — returns a stream of user activity events.",
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
            {
                "id": str(uuid.UUID("e1000004-0004-4000-8000-000000000004")),
                "name": "QueryTransactionStatus",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{wsdl_url}}",
                "headers": {
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": "\"urn:QueryTransactionStatus\"",
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
    <pay:QueryTransactionStatusRequest>
      <pay:TransactionId>{{transaction_id}}</pay:TransactionId>
    </pay:QueryTransactionStatusRequest>
  </soapenv:Body>
</soapenv:Envelope>""",
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                    {"type": "body_contains", "expected": "QueryTransactionStatusResponse", "path": "", "operator": "eq"},
                ],
                "captures": [
                    {"name": "txn_status", "source": "body", "path": "Status"},
                ],
                "tags": ["soap", "payment", "query"],
                "examples": [],
                "notes": "Polls the current settlement status of a transaction.",
                "items": [],
            },
            {
                "id": str(uuid.UUID("e1000004-0005-4000-8000-000000000005")),
                "name": "GetMerchantBalance",
                "is_folder": False,
                "kind": "request",
                "method": "POST",
                "url": "{{wsdl_url}}",
                "headers": {
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": "\"urn:GetMerchantBalance\"",
                },
                "body": """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:pay="urn:payment.example.com:v3">
  <soapenv:Header>
    <pay:Security>
      <pay:MerchantId>{{merchant_id}}</pay:MerchantId>
      <pay:Signature>{{secret_key}}</pay:Signature>
    </pay:Security>
  </soapenv:Header>
  <soapenv:Body>
    <pay:GetMerchantBalanceRequest>
      <pay:Currency>USD</pay:Currency>
    </pay:GetMerchantBalanceRequest>
  </soapenv:Body>
</soapenv:Envelope>""",
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "200", "path": "", "operator": "eq"},
                    {"type": "body_contains", "expected": "AvailableBalance", "path": "", "operator": "eq"},
                ],
                "captures": [],
                "tags": ["soap", "payment", "balance"],
                "examples": [],
                "notes": "Retrieve settled and pending balances for this merchant account.",
                "items": [],
            },
        ],
    }

    # 5. WebSocket — Realtime Trading Feed -----------------------------------------
    ws_collection = {
        "id": _COL_WS_ID,
        "name": "Realtime Trading Feed (WS)",
        "version": 1,
        "variables": [
            {"name": "ws_url", "value": "wss://stream.trading.example.com/v1", "enabled": True},
            {"name": "ws_token", "value": "ws_demo_token_replace_me", "enabled": True},
        ],
        "items": [
            {
                "id": str(uuid.UUID("f2000005-0001-4000-8000-000000000001")),
                "name": "Subscribe Market Data",
                "is_folder": False,
                "kind": "request",
                "method": "GET",
                "url": "{{ws_url}}/market",
                "headers": {
                    "Authorization": "Bearer {{ws_token}}",
                    "Sec-WebSocket-Protocol": "trading.v1",
                },
                "body": json.dumps({
                    "_ws_connect": True,
                    "subscribe": {"channels": ["ticker", "orderbook"], "symbols": ["BTC-USD", "ETH-USD", "SOL-USD"]},
                }),
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "101", "path": "", "operator": "eq"},
                ],
                "captures": [],
                "tags": ["websocket", "market", "subscribe"],
                "examples": [],
                "notes": "Opens a WS connection and subscribes to ticker + order-book for three symbols.",
                "items": [],
            },
            {
                "id": str(uuid.UUID("f2000005-0002-4000-8000-000000000002")),
                "name": "Place Market Order (WS)",
                "is_folder": False,
                "kind": "request",
                "method": "GET",
                "url": "{{ws_url}}/orders",
                "headers": {
                    "Authorization": "Bearer {{ws_token}}",
                    "Sec-WebSocket-Protocol": "trading.v1",
                },
                "body": json.dumps({
                    "_ws_connect": True,
                    "action": "place_order",
                    "payload": {"symbol": "BTC-USD", "side": "buy", "qty": 0.01, "type": "market"},
                }),
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "101", "path": "", "operator": "eq"},
                ],
                "captures": [
                    {"name": "ws_order_id", "source": "body", "path": "order_id"},
                ],
                "tags": ["websocket", "orders"],
                "examples": [],
                "notes": "Places a market buy order over persistent WS session.",
                "items": [],
            },
            {
                "id": str(uuid.UUID("f2000005-0003-4000-8000-000000000003")),
                "name": "Account Balance Stream",
                "is_folder": False,
                "kind": "request",
                "method": "GET",
                "url": "{{ws_url}}/account/balance",
                "headers": {
                    "Authorization": "Bearer {{ws_token}}",
                },
                "body": json.dumps({
                    "_ws_connect": True,
                    "subscribe": {"feed": "account_updates", "throttle_ms": 500},
                }),
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "101", "path": "", "operator": "eq"},
                ],
                "captures": [],
                "tags": ["websocket", "account"],
                "examples": [],
                "notes": "Streams real-time account balance updates at 2 Hz.",
                "items": [],
            },
            {
                "id": str(uuid.UUID("f2000005-0004-4000-8000-000000000004")),
                "name": "Ping / Heartbeat",
                "is_folder": False,
                "kind": "request",
                "method": "GET",
                "url": "{{ws_url}}/ping",
                "headers": {"Authorization": "Bearer {{ws_token}}"},
                "body": json.dumps({"_ws_connect": True, "type": "ping"}),
                "auth": {"type": "none"},
                "assertions": [
                    {"type": "status", "expected": "101", "path": "", "operator": "eq"},
                ],
                "captures": [],
                "tags": ["websocket", "health"],
                "examples": [],
                "notes": "Heartbeat frame — server should respond with pong within 1 s.",
                "items": [],
            },
        ],
    }

    for col_data in [rest_collection, graphql_collection, grpc_collection, soap_collection, ws_collection]:
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

    # 28 entries spread over ~14 days — varied methods, statuses, latencies
    entries: list[dict[str, Any]] = [
        # --- 14 days ago ---
        {
            "id": "a0000001-0001-4000-8000-000000000001",
            "method": "POST",
            "url": "https://api.shop.example.com/v2/auth/login",
            "status": 200,
            "elapsed_ms": 134.2,
            "timestamp": _ts(14, 9, 5),
            "request_headers": {"Content-Type": "application/json"},
            "response_headers": {"Content-Type": "application/json", "X-Request-Id": "req_auth_001"},
            "request_body": '{"email":"alice@example.com","password":"demo_pass_123"}',
            "response_body": '{"access_token":"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...","refresh_token":"rt_demo_001","expires_in":3600}',
        },
        {
            "id": "a0000001-0002-4000-8000-000000000002",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/users?page=1&limit=20",
            "status": 200,
            "elapsed_ms": 87.3,
            "timestamp": _ts(13, 14, 22),
            "request_headers": {"Accept": "application/json", "X-API-Key": "sk_test_demo_key_12345"},
            "response_headers": {"Content-Type": "application/json", "X-Request-Id": "req_abc1234"},
            "request_body": None,
            "response_body": '{"success":true,"data":[{"id":"usr_001","email":"alice@example.com"},{"id":"usr_002","email":"bob@example.com"},{"id":"usr_003","email":"carol@example.com"}],"total":142,"page":1}',
        },
        {
            "id": "a0000001-0003-4000-8000-000000000003",
            "method": "POST",
            "url": "https://api.shop.example.com/v2/users",
            "status": 201,
            "elapsed_ms": 143.6,
            "timestamp": _ts(13, 14, 35),
            "request_headers": {"Content-Type": "application/json"},
            "response_headers": {"Content-Type": "application/json", "Location": "/v2/users/usr_new_001"},
            "request_body": '{"email":"alice@example.com","first_name":"Alice","last_name":"Wonderland","role":"customer"}',
            "response_body": '{"id":"usr_new_001","email":"alice@example.com","role":"customer","created_at":"2026-05-20T14:35:00Z"}',
        },
        {
            "id": "a0000001-0004-4000-8000-000000000004",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/products?category=electronics&in_stock=true",
            "status": 200,
            "elapsed_ms": 62.1,
            "timestamp": _ts(12, 9, 15),
            "request_headers": {"Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json", "Cache-Control": "max-age=60"},
            "request_body": None,
            "response_body": '{"success":true,"data":[{"sku":"ELEC-001","name":"Wireless Mouse","price":49.99,"stock":234},{"sku":"ELEC-002","name":"Mechanical Keyboard","price":129.00,"stock":87},{"sku":"ELEC-003","name":"USB-C Hub","price":39.99,"stock":412}],"total":18}',
        },
        # --- 11-12 days ago ---
        {
            "id": "a0000001-0005-4000-8000-000000000005",
            "method": "POST",
            "url": "https://api.shop.example.com/v2/orders",
            "status": 201,
            "elapsed_ms": 312.4,
            "timestamp": _ts(11, 16, 45),
            "request_headers": {"Content-Type": "application/json", "Authorization": "Bearer sk_test_demo_key_12345"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": '{"user_id":"usr_001","items":[{"sku":"ELEC-001","qty":2,"unit_price":49.99},{"sku":"ELEC-002","qty":1,"unit_price":129.00}]}',
            "response_body": '{"order_id":"ord_abc123","status":"pending","total":228.98,"created_at":"2026-05-22T16:45:00Z"}',
        },
        {
            "id": "a0000001-0006-4000-8000-000000000006",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/health",
            "status": 200,
            "elapsed_ms": 12.7,
            "timestamp": _ts(11, 8, 0),
            "request_headers": {"Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"status":"ok","version":"2.5.0","db":"connected","redis":"connected","uptime_s":864721}',
        },
        {
            "id": "a0000001-0007-4000-8000-000000000007",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/users/usr_new_001",
            "status": 200,
            "elapsed_ms": 55.0,
            "timestamp": _ts(10, 11, 30),
            "request_headers": {"Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"id":"usr_new_001","email":"alice@example.com","role":"customer","last_login":"2026-05-23T11:00:00Z","orders_count":3}',
        },
        {
            "id": "a0000001-0008-4000-8000-000000000008",
            "method": "PATCH",
            "url": "https://api.shop.example.com/v2/users/usr_new_001",
            "status": 200,
            "elapsed_ms": 98.2,
            "timestamp": _ts(10, 11, 45),
            "request_headers": {"Content-Type": "application/json"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": '{"last_name":"Smith","role":"admin"}',
            "response_body": '{"id":"usr_new_001","last_name":"Smith","role":"admin","updated_at":"2026-05-23T11:45:00Z"}',
        },
        # --- 8-9 days ago ---
        {
            "id": "a0000001-0009-4000-8000-000000000009",
            "method": "POST",
            "url": "https://api.github.com/graphql",
            "status": 200,
            "elapsed_ms": 185.9,
            "timestamp": _ts(9, 14, 0),
            "request_headers": {"Content-Type": "application/json", "Authorization": "bearer ghp_demo_token"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": '{"query":"query { viewer { login name followers { totalCount } } }"}',
            "response_body": '{"data":{"viewer":{"login":"alice-dev","name":"Alice Smith","followers":{"totalCount":318}}}}',
        },
        {
            "id": "a0000001-000a-4000-8000-00000000000a",
            "method": "POST",
            "url": "https://api.github.com/graphql",
            "status": 200,
            "elapsed_ms": 221.4,
            "timestamp": _ts(9, 14, 15),
            "request_headers": {"Content-Type": "application/json", "Authorization": "bearer ghp_demo_token"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": '{"query":"query($login:String!,$first:Int!){user(login:$login){repositories(first:$first,orderBy:{field:STARGAZERS,direction:DESC}){nodes{name stargazerCount forkCount}}}}","variables":{"login":"alice-dev","first":10}}',
            "response_body": '{"data":{"user":{"repositories":{"nodes":[{"name":"theridion","stargazerCount":1842,"forkCount":203},{"name":"api-hunter","stargazerCount":914,"forkCount":87}]}}}}',
        },
        {
            "id": "a0000001-000b-4000-8000-00000000000b",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/orders?status=pending&limit=10",
            "status": 200,
            "elapsed_ms": 74.4,
            "timestamp": _ts(8, 10, 20),
            "request_headers": {"Accept": "application/json", "Authorization": "Bearer sk_test_demo_key_12345"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"success":true,"data":[{"order_id":"ord_abc123","status":"pending","total":228.98},{"order_id":"ord_def456","status":"pending","total":49.99}],"total":7}',
        },
        {
            "id": "a0000001-000c-4000-8000-00000000000c",
            "method": "POST",
            "url": "https://payments.example.com/ws/v3?wsdl",
            "status": 200,
            "elapsed_ms": 241.0,
            "timestamp": _ts(8, 15, 10),
            "request_headers": {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '"urn:AuthorizeCard"'},
            "response_headers": {"Content-Type": "text/xml; charset=utf-8"},
            "request_body": '<?xml version="1.0"?><soapenv:Envelope><soapenv:Body><AuthorizeCardRequest><Amount>99.99</Amount><Currency>USD</Currency></AuthorizeCardRequest></soapenv:Body></soapenv:Envelope>',
            "response_body": '<?xml version="1.0"?><soapenv:Envelope><soapenv:Body><AuthorizeCardResponse><Status>APPROVED</Status><AuthCode>AUTH_7791</AuthCode></AuthorizeCardResponse></soapenv:Body></soapenv:Envelope>',
        },
        # --- 6-7 days ago ---
        {
            "id": "a0000001-000d-4000-8000-00000000000d",
            "method": "POST",
            "url": "https://users.internal.example.com:50051",
            "status": 200,
            "elapsed_ms": 18.3,
            "timestamp": _ts(7, 11, 0),
            "request_headers": {"content-type": "application/grpc+json"},
            "response_headers": {"content-type": "application/grpc+json", "grpc-status": "0"},
            "request_body": '{"_grpc_method":"user.UserService/GetUser","user_id":"usr_7f4a1b2c"}',
            "response_body": '{"user_id":"usr_7f4a1b2c","display_name":"Bob Marley","email":"bob@example.com","created_at":"2026-01-10T09:00:00Z"}',
        },
        {
            "id": "a0000001-000e-4000-8000-00000000000e",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/health",
            "status": 200,
            "elapsed_ms": 11.3,
            "timestamp": _ts(6, 8, 0),
            "request_headers": {"Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"status":"ok","version":"2.5.0"}',
        },
        {
            "id": "a0000001-000f-4000-8000-00000000000f",
            "method": "DELETE",
            "url": "https://api.shop.example.com/v2/users/usr_old_999",
            "status": 204,
            "elapsed_ms": 67.8,
            "timestamp": _ts(6, 13, 40),
            "request_headers": {"X-API-Key": "sk_test_demo_key_12345"},
            "response_headers": {},
            "request_body": None,
            "response_body": "",
        },
        # --- 4-5 days ago ---
        {
            "id": "a0000001-0010-4000-8000-000000000010",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/products/ELEC-999",
            "status": 404,
            "elapsed_ms": 44.5,
            "timestamp": _ts(5, 16, 5),
            "request_headers": {"Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"error":"product_not_found","message":"Product ELEC-999 not found or discontinued"}',
        },
        {
            "id": "a0000001-0011-4000-8000-000000000011",
            "method": "POST",
            "url": "https://api.shop.example.com/v2/orders",
            "status": 422,
            "elapsed_ms": 89.1,
            "timestamp": _ts(5, 10, 15),
            "request_headers": {"Content-Type": "application/json"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": '{"user_id":"usr_001","items":[]}',
            "response_body": '{"error":"validation_failed","message":"items must not be empty","field":"items"}',
        },
        {
            "id": "a0000001-0012-4000-8000-000000000012",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/products/search?q=bluetooth+headphones&limit=20",
            "status": 200,
            "elapsed_ms": 148.7,
            "timestamp": _ts(4, 14, 30),
            "request_headers": {"Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json", "Cache-Control": "max-age=30"},
            "request_body": None,
            "response_body": '{"results":[{"sku":"AUDIO-001","name":"BT Headphones Pro","price":89.99,"relevance":0.97},{"sku":"AUDIO-002","name":"Wireless Earbuds","price":59.99,"relevance":0.91}],"total":14,"query_time_ms":12}',
        },
        {
            "id": "a0000001-0013-4000-8000-000000000013",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/promotions/coupons?active=true",
            "status": 200,
            "elapsed_ms": 38.9,
            "timestamp": _ts(4, 15, 0),
            "request_headers": {"Accept": "application/json", "Authorization": "Bearer sk_test_demo_key_12345"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"coupons":[{"code":"SUMMER20","discount":0.2,"type":"percent","expires":"2026-08-31"},{"code":"FREESHIP","discount":0.0,"type":"shipping","expires":"2026-06-30"}],"total":2}',
        },
        # --- 2-3 days ago ---
        {
            "id": "a0000001-0014-4000-8000-000000000014",
            "method": "POST",
            "url": "https://api.shop.example.com/v2/auth/refresh",
            "status": 200,
            "elapsed_ms": 76.2,
            "timestamp": _ts(3, 9, 0),
            "request_headers": {"Content-Type": "application/json"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": '{"refresh_token":"rt_demo_001"}',
            "response_body": '{"access_token":"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...new","expires_in":3600}',
        },
        {
            "id": "a0000001-0015-4000-8000-000000000015",
            "method": "PUT",
            "url": "https://api.shop.example.com/v2/products/ELEC-001",
            "status": 200,
            "elapsed_ms": 167.3,
            "timestamp": _ts(3, 11, 20),
            "request_headers": {"Content-Type": "application/json", "Authorization": "Bearer sk_test_demo_key_12345"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": '{"price":44.99,"stock":198,"description":"Ergonomic wireless mouse with 6-button layout"}',
            "response_body": '{"sku":"ELEC-001","name":"Wireless Mouse","price":44.99,"stock":198,"updated_at":"2026-05-30T11:20:00Z"}',
        },
        {
            "id": "a0000001-0016-4000-8000-000000000016",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/orders/ord_abc123",
            "status": 200,
            "elapsed_ms": 59.4,
            "timestamp": _ts(3, 14, 10),
            "request_headers": {"Accept": "application/json", "Authorization": "Bearer sk_test_demo_key_12345"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"order_id":"ord_abc123","status":"shipped","total":228.98,"items":[{"sku":"ELEC-001","qty":2},{"sku":"ELEC-002","qty":1}],"tracking":"TRK7890123"}',
        },
        {
            "id": "a0000001-0017-4000-8000-000000000017",
            "method": "POST",
            "url": "https://users.internal.example.com:50051",
            "status": 200,
            "elapsed_ms": 22.7,
            "timestamp": _ts(2, 10, 0),
            "request_headers": {"content-type": "application/grpc+json"},
            "response_headers": {"content-type": "application/grpc+json", "grpc-status": "0"},
            "request_body": '{"_grpc_method":"user.UserService/ListUsers","page_size":20,"page_token":""}',
            "response_body": '{"users":[{"user_id":"usr_001","display_name":"Alice Smith"},{"user_id":"usr_002","display_name":"Bob Marley"}],"next_page_token":"tok_page2","total_count":142}',
        },
        {
            "id": "a0000001-0018-4000-8000-000000000018",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/users?page=2&limit=20",
            "status": 200,
            "elapsed_ms": 73.1,
            "timestamp": _ts(2, 10, 30),
            "request_headers": {"Accept": "application/json", "X-API-Key": "sk_test_demo_key_12345"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"success":true,"data":[{"id":"usr_021","email":"david@example.com"},{"id":"usr_022","email":"eve@example.com"}],"total":142,"page":2}',
        },
        # --- Yesterday / today ---
        {
            "id": "a0000001-0019-4000-8000-000000000019",
            "method": "POST",
            "url": "https://payments.example.com/ws/v3?wsdl",
            "status": 200,
            "elapsed_ms": 198.4,
            "timestamp": _ts(1, 14, 5),
            "request_headers": {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '"urn:CapturePayment"'},
            "response_headers": {"Content-Type": "text/xml; charset=utf-8"},
            "request_body": '<?xml version="1.0"?><soapenv:Envelope><soapenv:Body><CapturePaymentRequest><AuthCode>AUTH_7791</AuthCode><Amount>99.99</Amount></CapturePaymentRequest></soapenv:Body></soapenv:Envelope>',
            "response_body": '<?xml version="1.0"?><soapenv:Envelope><soapenv:Body><CapturePaymentResponse><Status>CAPTURED</Status><TransactionId>TXN_20241</TransactionId></CapturePaymentResponse></soapenv:Body></soapenv:Envelope>',
        },
        {
            "id": "a0000001-001a-4000-8000-00000000001a",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/health",
            "status": 503,
            "elapsed_ms": 5002.1,
            "timestamp": _ts(1, 3, 14),
            "request_headers": {"Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json", "Retry-After": "30"},
            "request_body": None,
            "response_body": '{"status":"degraded","db":"connected","redis":"timeout","message":"Redis cluster is recovering"}',
        },
        {
            "id": "a0000001-001b-4000-8000-00000000001b",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/health",
            "status": 200,
            "elapsed_ms": 14.8,
            "timestamp": _ts(1, 3, 45),
            "request_headers": {"Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"status":"ok","version":"2.5.0","db":"connected","redis":"connected"}',
        },
        {
            "id": "a0000001-001c-4000-8000-00000000001c",
            "method": "HEAD",
            "url": "https://api.shop.example.com/v2/products/ELEC-003",
            "status": 200,
            "elapsed_ms": 8.3,
            "timestamp": _ts(0.5, 8, 15),
            "request_headers": {"Accept": "application/json"},
            "response_headers": {"Content-Type": "application/json", "X-Cache": "HIT", "ETag": '"abc123def"'},
            "request_body": None,
            "response_body": "",
        },
        {
            "id": "a0000001-001d-4000-8000-00000000001d",
            "method": "GET",
            "url": "https://api.shop.example.com/v2/users?page=1&limit=20",
            "status": 200,
            "elapsed_ms": 91.6,
            "timestamp": _ts(0.1, 9, 0),
            "request_headers": {"Accept": "application/json", "X-API-Key": "sk_test_demo_key_12345"},
            "response_headers": {"Content-Type": "application/json"},
            "request_body": None,
            "response_body": '{"success":true,"data":[{"id":"usr_001","email":"alice@example.com"},{"id":"usr_002","email":"bob@example.com"}],"total":143,"page":1}',
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

    def _timeline(duration_s: int, rps_base: float, lat_base: float, error_rate: float = 0.0,
                  ramp_s: int = 10, max_vu: int = 20) -> list[dict]:
        import math, random
        random.seed(42)
        pts = []
        for s in range(duration_s):
            # Natural ramp-up, then plateau, slight cooldown in last 10%
            ramp = min(1.0, (s + 1) / max(ramp_s, 1))
            cooldown = 1.0 if s < duration_s * 0.9 else max(0.6, 1.0 - (s - duration_s * 0.9) / (duration_s * 0.1) * 0.4)
            rps = round(rps_base * ramp * cooldown + random.gauss(0, rps_base * 0.04), 2)
            lat = round(lat_base * (1 + 0.12 * math.sin(s / 4.2) + 0.06 * math.sin(s / 11.0))
                        + random.gauss(0, lat_base * 0.08), 2)
            errs = round(rps * error_rate, 4)
            active_vu = min(s + 1, max_vu) if s < ramp_s else max_vu
            pts.append({
                "second": s,
                "rps": max(0.0, rps),
                "avg_latency_ms": max(0.5, lat),
                "error_count": int(errs),
                "active_users": active_vu,
                "error_rate": error_rate,
                "p95_ms": round(max(0.5, lat) * 1.45, 2),
            })
        return pts

    results = [
        # Smoke test — fast, clean
        {
            "id": "b0000001-0001-4000-8000-000000000001",
            "url": "https://api.shop.example.com/v2/health",
            "method": "GET",
            "virtual_users": 5,
            "duration_seconds": 60,
            "ramp_up_seconds": 5,
            "started_at": _ts(14, 10, 0),
            "collection_name": "E-Commerce API",
            "label": "Smoke — Health Check",
            "total_requests": 2487,
            "successful": 2487,
            "failed": 0,
            "errors": {},
            "avg_latency_ms": 13.8,
            "min_latency_ms": 7.2,
            "max_latency_ms": 41.6,
            "p50_ms": 12.4,
            "p75_ms": 16.9,
            "p90_ms": 21.3,
            "p95_ms": 26.8,
            "p99_ms": 38.4,
            "requests_per_second": 41.45,
            "duration_seconds": 60.0,
            "timeline": _timeline(60, 41.0, 13.8, ramp_s=5, max_vu=5),
        },
        # Baseline load — moderate traffic, slightly high p99
        {
            "id": "b0000001-0002-4000-8000-000000000002",
            "url": "https://api.shop.example.com/v2/products?category=electronics",
            "method": "GET",
            "virtual_users": 25,
            "duration_seconds": 120,
            "ramp_up_seconds": 15,
            "started_at": _ts(11, 14, 0),
            "collection_name": "E-Commerce API",
            "label": "Baseline — List Products (2 min)",
            "total_requests": 16_847,
            "successful": 16_829,
            "failed": 18,
            "errors": {"ConnectionTimeout": 18},
            "avg_latency_ms": 67.4,
            "min_latency_ms": 29.8,
            "max_latency_ms": 1187.2,
            "p50_ms": 61.7,
            "p75_ms": 86.3,
            "p90_ms": 121.4,
            "p95_ms": 182.6,
            "p99_ms": 487.3,
            "requests_per_second": 140.39,
            "duration_seconds": 120.0,
            "timeline": _timeline(120, 140.0, 67.0, 0.0011, ramp_s=15, max_vu=25),
        },
        # Spike test — sudden burst, latency spike, recovery
        {
            "id": "b0000001-0003-4000-8000-000000000003",
            "url": "https://api.shop.example.com/v2/users",
            "method": "GET",
            "virtual_users": 150,
            "duration_seconds": 90,
            "ramp_up_seconds": 5,
            "started_at": _ts(9, 16, 0),
            "collection_name": "E-Commerce API",
            "label": "Spike — User List Burst",
            "total_requests": 31_204,
            "successful": 30_891,
            "failed": 313,
            "errors": {"ConnectError": 187, "ConnectionTimeout": 126},
            "avg_latency_ms": 128.4,
            "min_latency_ms": 18.2,
            "max_latency_ms": 4321.0,
            "p50_ms": 104.7,
            "p75_ms": 166.8,
            "p90_ms": 241.3,
            "p95_ms": 398.7,
            "p99_ms": 1243.6,
            "requests_per_second": 346.71,
            "duration_seconds": 90.0,
            "timeline": _timeline(90, 345.0, 128.0, 0.010, ramp_s=5, max_vu=150),
        },
        # Stress test — high VU, elevated errors
        {
            "id": "b0000001-0004-4000-8000-000000000004",
            "url": "https://api.shop.example.com/v2/orders",
            "method": "POST",
            "virtual_users": 100,
            "duration_seconds": 180,
            "ramp_up_seconds": 25,
            "started_at": _ts(7, 9, 0),
            "collection_name": "E-Commerce API",
            "label": "Stress — Place Order (3 min)",
            "total_requests": 42_187,
            "successful": 39_412,
            "failed": 2775,
            "errors": {"ConnectError": 1542, "ConnectionTimeout": 1017, "HTTP_503": 216},
            "avg_latency_ms": 337.6,
            "min_latency_ms": 44.1,
            "max_latency_ms": 9641.2,
            "p50_ms": 284.7,
            "p75_ms": 418.3,
            "p90_ms": 609.4,
            "p95_ms": 836.8,
            "p99_ms": 2287.4,
            "requests_per_second": 234.37,
            "duration_seconds": 180.0,
            "timeline": _timeline(180, 230.0, 337.0, 0.066, ramp_s=25, max_vu=100),
        },
        # Soak test — 5 minutes, stable throughput
        {
            "id": "b0000001-0005-4000-8000-000000000005",
            "url": "https://api.shop.example.com/v2/users",
            "method": "GET",
            "virtual_users": 15,
            "duration_seconds": 300,
            "ramp_up_seconds": 20,
            "started_at": _ts(4, 11, 0),
            "collection_name": "E-Commerce API",
            "label": "Soak — List Users (5 min)",
            "total_requests": 134_218,
            "successful": 134_162,
            "failed": 56,
            "errors": {"ConnectionTimeout": 56},
            "avg_latency_ms": 33.4,
            "min_latency_ms": 9.1,
            "max_latency_ms": 743.8,
            "p50_ms": 29.8,
            "p75_ms": 43.1,
            "p90_ms": 61.4,
            "p95_ms": 82.7,
            "p99_ms": 207.3,
            "requests_per_second": 447.39,
            "duration_seconds": 300.0,
            "timeline": _timeline(300, 445.0, 33.0, 0.0004, ramp_s=20, max_vu=15),
        },
        # GraphQL — ramp and sustained
        {
            "id": "b0000001-0006-4000-8000-000000000006",
            "url": "https://api.github.com/graphql",
            "method": "POST",
            "virtual_users": 30,
            "duration_seconds": 120,
            "ramp_up_seconds": 20,
            "started_at": _ts(2, 15, 0),
            "collection_name": "GitHub GraphQL API",
            "label": "Baseline — GraphQL Viewer Query",
            "total_requests": 8_941,
            "successful": 8_924,
            "failed": 17,
            "errors": {"HTTP_429": 17},
            "avg_latency_ms": 192.3,
            "min_latency_ms": 87.4,
            "max_latency_ms": 2148.7,
            "p50_ms": 178.6,
            "p75_ms": 241.4,
            "p90_ms": 318.7,
            "p95_ms": 412.3,
            "p99_ms": 897.4,
            "requests_per_second": 74.51,
            "duration_seconds": 120.0,
            "timeline": _timeline(120, 74.0, 192.0, 0.0019, ramp_s=20, max_vu=30),
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
        # Clean baseline — health endpoint, no findings
        {
            "id": "c0000001-0001-4000-8000-000000000001",
            "url": "https://api.shop.example.com/v2/health",
            "method": "GET",
            "scan_types_run": ["sql_injection", "xss", "auth_bypass", "rate_limit"],
            "score": 98,
            "elapsed_ms": 1243.7,
            "started_at": _ts(14, 15, 0),
            "collection_name": "E-Commerce API",
            "findings": [
                {
                    "scan_type": "xss",
                    "severity": "info",
                    "title": "Missing X-Content-Type-Options Header",
                    "evidence": "Response headers do not include X-Content-Type-Options: nosniff.",
                    "description": (
                        "Adding X-Content-Type-Options: nosniff prevents MIME-sniffing attacks in older "
                        "browsers. Low risk for pure JSON APIs but recommended as a defense-in-depth measure."
                    ),
                },
            ],
        },
        # Product search — reflected XSS in error body
        {
            "id": "c0000001-0002-4000-8000-000000000002",
            "url": "https://api.shop.example.com/v2/products/search",
            "method": "GET",
            "scan_types_run": ["sql_injection", "xss", "rate_limit"],
            "score": 72,
            "elapsed_ms": 3874.5,
            "started_at": _ts(11, 14, 30),
            "collection_name": "E-Commerce API",
            "findings": [
                {
                    "scan_type": "xss",
                    "severity": "medium",
                    "title": "Reflected Parameter in Error Response",
                    "evidence": "GET /v2/products/search?q=<script>alert(1)</script> → 400: invalid query: <script>alert(1)</script> near character 0.",
                    "description": (
                        "The 'q' query parameter value is reflected unencoded in the 400 error response body. "
                        "An attacker could craft a link that injects script into victim's browser if the API "
                        "response is rendered in an HTML context. Apply output encoding for all user-supplied "
                        "values in error messages."
                    ),
                },
                {
                    "scan_type": "rate_limit",
                    "severity": "medium",
                    "title": "Search Endpoint Lacks Throttling",
                    "evidence": "100 rapid requests in 5 s returned 200 each; no 429 encountered.",
                    "description": (
                        "The /v2/products/search endpoint does not enforce per-IP rate limiting. "
                        "This allows automated crawling of the full product catalogue. "
                        "Implement token-bucket or sliding-window rate limiting (suggested: 60 req/min per IP)."
                    ),
                },
                {
                    "scan_type": "sql_injection",
                    "severity": "info",
                    "title": "SQL Error Strings Suppressed",
                    "evidence": "No SQL dialect errors observed across 12 injection payloads.",
                    "description": (
                        "Error messages do not leak SQL dialect details. Continue suppressing internal "
                        "stack traces and ensure dev/staging environments share the same error-handling config."
                    ),
                },
            ],
        },
        # Users endpoint — critical SQLi + auth bypass
        {
            "id": "c0000001-0003-4000-8000-000000000003",
            "url": "https://api.shop.example.com/v2/users",
            "method": "GET",
            "scan_types_run": ["sql_injection", "xss", "auth_bypass", "rate_limit"],
            "score": 28,
            "elapsed_ms": 9214.8,
            "started_at": _ts(9, 10, 0),
            "collection_name": "E-Commerce API",
            "findings": [
                {
                    "scan_type": "sql_injection",
                    "severity": "critical",
                    "title": "SQL Injection via 'search' Parameter",
                    "evidence": (
                        "GET /v2/users?search=' OR '1'='1 → 200 OK, returns all 143 users. "
                        "Debug header X-Debug-Query leaked: SELECT * FROM users WHERE name LIKE ''%' OR '1'='1%''."
                    ),
                    "description": (
                        "The 'search' query parameter is directly interpolated into a SQL query without "
                        "parameterization. An attacker can enumerate all users, exfiltrate PII, or execute "
                        "arbitrary SQL including DROP TABLE. Immediate fix required: use parameterized queries "
                        "or an ORM; strip X-Debug-Query header from non-localhost responses."
                    ),
                },
                {
                    "scan_type": "auth_bypass",
                    "severity": "high",
                    "title": "Unauthenticated Access to User List",
                    "evidence": "GET /v2/users (no Authorization header) → 200 OK with full PII payload including emails, roles and last_login timestamps.",
                    "description": (
                        "The /v2/users endpoint does not require authentication. Any internet-accessible "
                        "caller can enumerate all registered users. Enforce bearer token middleware on all "
                        "/v2/users/* routes and add integration tests to assert 401 for unauthenticated calls."
                    ),
                },
                {
                    "scan_type": "rate_limit",
                    "severity": "medium",
                    "title": "No Rate Limiting — User Enumeration Vector",
                    "evidence": "50 rapid requests per second to /v2/users returned 200 each; no 429 or CAPTCHA challenge observed.",
                    "description": (
                        "Combined with the auth bypass, the absence of rate limiting enables automated data "
                        "exfiltration of the entire user base within seconds. Implement per-IP rate limiting "
                        "at 60 req/min minimum; consider adding bot-detection headers (e.g. Cloudflare Turnstile)."
                    ),
                },
                {
                    "scan_type": "xss",
                    "severity": "low",
                    "title": "Missing Content-Security-Policy Header",
                    "evidence": "Response headers: Content-Security-Policy absent across all /v2/users responses.",
                    "description": (
                        "A restrictive CSP header reduces the blast radius if XSS is introduced. "
                        "Recommended: Content-Security-Policy: default-src 'none'; frame-ancestors 'none'."
                    ),
                },
                {
                    "scan_type": "auth_bypass",
                    "severity": "low",
                    "title": "CORS Wildcard on Sensitive Route",
                    "evidence": "Response includes Access-Control-Allow-Origin: * for /v2/users.",
                    "description": (
                        "A wildcard CORS policy on routes returning PII is overly permissive. "
                        "Restrict to known first-party origins (e.g. https://shop.example.com)."
                    ),
                },
            ],
        },
        # Order placement — medium findings fixed in re-scan
        {
            "id": "c0000001-0004-4000-8000-000000000004",
            "url": "https://api.shop.example.com/v2/orders",
            "method": "POST",
            "scan_types_run": ["sql_injection", "xss", "auth_bypass", "rate_limit"],
            "score": 81,
            "elapsed_ms": 5341.2,
            "started_at": _ts(6, 11, 0),
            "collection_name": "E-Commerce API",
            "findings": [
                {
                    "scan_type": "rate_limit",
                    "severity": "medium",
                    "title": "Order Submission Not Rate-Limited Per User",
                    "evidence": "10 order submissions in 1 s from same user_id returned 201 each; no per-user throttle observed.",
                    "description": (
                        "The checkout endpoint does not enforce per-user rate limiting. An attacker who "
                        "obtains a valid token could flood the payment system. Add a per-user limit of "
                        "~5 orders per minute and an idempotency key mechanism."
                    ),
                },
                {
                    "scan_type": "xss",
                    "severity": "info",
                    "title": "No Strict-Transport-Security Header",
                    "evidence": "Strict-Transport-Security header absent from all /v2/orders responses.",
                    "description": (
                        "Configuring HSTS (Strict-Transport-Security: max-age=31536000; includeSubDomains) "
                        "prevents protocol-downgrade attacks. Ensure HTTPS is enforced before enabling."
                    ),
                },
            ],
        },
        # Auth endpoint — hardened, clean re-scan
        {
            "id": "c0000001-0005-4000-8000-000000000005",
            "url": "https://api.shop.example.com/v2/auth/login",
            "method": "POST",
            "scan_types_run": ["auth_bypass", "rate_limit", "sql_injection"],
            "score": 96,
            "elapsed_ms": 2187.4,
            "started_at": _ts(3, 10, 0),
            "collection_name": "E-Commerce API",
            "findings": [
                {
                    "scan_type": "auth_bypass",
                    "severity": "info",
                    "title": "Username Enumeration via Timing Difference",
                    "evidence": "Login with existing email averages 142 ms; non-existent email averages 14 ms — 10× timing delta detectable.",
                    "description": (
                        "The difference in response time between known and unknown usernames enables "
                        "user enumeration via timing oracle. Use a constant-time password check and ensure "
                        "all codepaths (found/not found) take the same wall-clock time by computing bcrypt "
                        "even for non-existent users."
                    ),
                },
            ],
        },
        # Latest re-scan of users — SQLi patched, score improved
        {
            "id": "c0000001-0006-4000-8000-000000000006",
            "url": "https://api.shop.example.com/v2/users",
            "method": "GET",
            "scan_types_run": ["sql_injection", "xss", "auth_bypass", "rate_limit"],
            "score": 87,
            "elapsed_ms": 4021.3,
            "started_at": _ts(1, 14, 0),
            "collection_name": "E-Commerce API",
            "findings": [
                {
                    "scan_type": "rate_limit",
                    "severity": "medium",
                    "title": "No Rate Limiting — Partially Remediated",
                    "evidence": "25 req/s now returns 429 after 10 requests; IP ban window is only 10 s (too short).",
                    "description": (
                        "Rate limiting is now enforced but the block window (10 s) is insufficient to deter "
                        "scrapers. Extend to 60 s exponential back-off and add account-level limits for "
                        "authenticated callers in addition to the IP-level throttle."
                    ),
                },
                {
                    "scan_type": "xss",
                    "severity": "low",
                    "title": "Missing Content-Security-Policy Header",
                    "evidence": "CSP header still absent from /v2/users responses.",
                    "description": "Carry-over from previous scan — CSP header not yet deployed to production.",
                },
            ],
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
_MON_GRAPHQL_ID     = "d2222222-0004-4000-8000-000000000004"
_MON_PAYMENT_ID     = "d2222222-0005-4000-8000-000000000005"
_MON_GRPC_ID        = "d2222222-0006-4000-8000-000000000006"

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
            "name": "Health Check — Production",
            "collection_id": _COL_REST_ID,
            "environment_id": _ENV_PRODUCTION_ID,
            "cron": "*/5 * * * *",
            "enabled": True,
            "last_run": _ts(0.004, 0, 0),   # ~6 min ago
            "last_status": "passed",
            "last_passed": 8,
            "last_failed": 0,
            "last_duration_ms": 13.8,
            "uptime_percent": 99.97,
            "consecutive_failures": 0,
        },
        {
            "id": _MON_USERS_ID,
            "name": "User API — Staging Hourly",
            "collection_id": _COL_REST_ID,
            "environment_id": _ENV_STAGING_ID,
            "cron": "0 * * * *",
            "enabled": True,
            "last_run": _ts(0.042, 0, 0),   # ~1 h ago
            "last_status": "passed",
            "last_passed": 10,
            "last_failed": 0,
            "last_duration_ms": 91.4,
            "uptime_percent": 98.34,
            "consecutive_failures": 0,
        },
        {
            "id": _MON_ORDERS_ID,
            "name": "Payment Gateway — Daily Smoke",
            "collection_id": _COL_SOAP_ID,
            "environment_id": _ENV_STAGING_ID,
            "cron": "0 6 * * *",
            "enabled": True,
            "last_run": _ts(1.25, 6, 0),    # yesterday at 06:00
            "last_status": "passed",
            "last_passed": 3,
            "last_failed": 0,
            "last_duration_ms": 243.7,
            "uptime_percent": 100.0,
            "consecutive_failures": 0,
        },
        {
            "id": _MON_GRAPHQL_ID,
            "name": "GitHub GraphQL — Viewer Check",
            "collection_id": _COL_GRAPHQL_ID,
            "environment_id": _ENV_GRAPHQL_ID,
            "cron": "*/15 * * * *",
            "enabled": True,
            "last_run": _ts(0.011, 0, 0),   # ~15 min ago
            "last_status": "passed",
            "last_passed": 3,
            "last_failed": 0,
            "last_duration_ms": 187.2,
            "uptime_percent": 99.61,
            "consecutive_failures": 0,
        },
        {
            "id": _MON_PAYMENT_ID,
            "name": "E-Commerce API — Full Suite",
            "collection_id": _COL_REST_ID,
            "environment_id": _ENV_PRODUCTION_ID,
            "cron": "0 */4 * * *",
            "enabled": True,
            "last_run": _ts(0.167, 0, 0),   # ~4 h ago
            "last_status": "failed",
            "last_passed": 9,
            "last_failed": 1,
            "last_duration_ms": 1843.1,
            "uptime_percent": 94.12,
            "consecutive_failures": 1,
        },
        {
            "id": _MON_GRPC_ID,
            "name": "User gRPC Service — Health",
            "collection_id": _COL_GRPC_ID,
            "environment_id": _ENV_STAGING_ID,
            "cron": "*/30 * * * *",
            "enabled": False,
            "last_run": _ts(2, 14, 0),
            "last_status": "passed",
            "last_passed": 3,
            "last_failed": 0,
            "last_duration_ms": 22.6,
            "uptime_percent": 100.0,
            "consecutive_failures": 0,
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
                "method": "POST",
                "path": "/v2/auth/login",
                "query": "",
                "request_headers": {"Content-Type": "application/json"},
                "request_body": json.dumps({"email": "alice@example.com", "password": "[REDACTED]"}),
                "status": 200,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": json.dumps({"access_token": "eyJ0...", "refresh_token": "rt_demo", "expires_in": 3600}),
                "elapsed_ms": 134.2,
                "timestamp": _ts(7, 9, 58),
            },
            {
                "method": "GET",
                "path": "/v2/health",
                "query": "",
                "request_headers": {"Accept": "application/json"},
                "request_body": None,
                "status": 200,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": json.dumps({"status": "ok", "version": "2.5.0", "db": "connected", "redis": "connected"}),
                "elapsed_ms": 13.8,
                "timestamp": _ts(7, 10, 0),
            },
            {
                "method": "GET",
                "path": "/v2/users",
                "query": "page=1&limit=20",
                "request_headers": {"Accept": "application/json", "X-API-Key": "sk_test_demo_key_12345"},
                "request_body": None,
                "status": 200,
                "response_headers": {"Content-Type": "application/json", "X-RateLimit-Remaining": "59"},
                "response_body": json.dumps({
                    "success": True,
                    "data": [
                        {"id": "usr_001", "email": "alice@example.com", "role": "admin", "last_login": "2026-05-31T08:00:00Z"},
                        {"id": "usr_002", "email": "bob@example.com", "role": "customer", "last_login": "2026-05-30T17:42:00Z"},
                        {"id": "usr_003", "email": "carol@example.com", "role": "customer", "last_login": "2026-05-29T12:11:00Z"},
                        {"id": "usr_004", "email": "david@example.com", "role": "moderator", "last_login": "2026-05-28T09:00:00Z"},
                    ],
                    "total": 143,
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
                    "data": [
                        {"sku": "ELEC-001", "name": "Wireless Mouse", "price": 44.99, "stock": 198},
                        {"sku": "ELEC-002", "name": "Mechanical Keyboard", "price": 129.00, "stock": 87},
                        {"sku": "ELEC-003", "name": "USB-C Hub 7-port", "price": 39.99, "stock": 412},
                        {"sku": "AUDIO-001", "name": "BT Headphones Pro", "price": 89.99, "stock": 53},
                    ],
                    "total": 18,
                    "page": 1,
                }),
                "elapsed_ms": 62.1,
                "timestamp": _ts(7, 10, 2),
            },
            {
                "method": "GET",
                "path": "/v2/products/search",
                "query": "q=bluetooth&limit=5",
                "request_headers": {"Accept": "application/json"},
                "request_body": None,
                "status": 200,
                "response_headers": {"Content-Type": "application/json", "Cache-Control": "max-age=30"},
                "response_body": json.dumps({
                    "results": [
                        {"sku": "AUDIO-001", "name": "BT Headphones Pro", "price": 89.99, "relevance": 0.97},
                        {"sku": "AUDIO-002", "name": "Wireless Earbuds", "price": 59.99, "relevance": 0.91},
                    ],
                    "total": 7,
                    "query_time_ms": 11,
                }),
                "elapsed_ms": 48.3,
                "timestamp": _ts(7, 10, 3),
            },
            {
                "method": "POST",
                "path": "/v2/orders",
                "query": "",
                "request_headers": {"Content-Type": "application/json", "Authorization": "Bearer eyJ0..."},
                "request_body": json.dumps({
                    "user_id": "usr_001",
                    "items": [
                        {"sku": "ELEC-001", "qty": 2, "unit_price": 44.99},
                        {"sku": "AUDIO-001", "qty": 1, "unit_price": 89.99},
                    ],
                    "coupon_code": "SUMMER20",
                }),
                "status": 201,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": json.dumps({
                    "order_id": "ord_demo_042",
                    "status": "pending",
                    "subtotal": 179.97,
                    "discount": 35.99,
                    "total": 143.98,
                    "created_at": "2026-05-25T10:03:00Z",
                }),
                "elapsed_ms": 287.4,
                "timestamp": _ts(7, 10, 4),
            },
            {
                "method": "GET",
                "path": "/v2/orders/ord_demo_042",
                "query": "",
                "request_headers": {"Accept": "application/json", "Authorization": "Bearer eyJ0..."},
                "request_body": None,
                "status": 200,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": json.dumps({
                    "order_id": "ord_demo_042",
                    "status": "processing",
                    "items": [{"sku": "ELEC-001", "qty": 2}, {"sku": "AUDIO-001", "qty": 1}],
                    "total": 143.98,
                    "tracking": None,
                }),
                "elapsed_ms": 57.8,
                "timestamp": _ts(7, 10, 5),
            },
            {
                "method": "GET",
                "path": "/v2/promotions/coupons",
                "query": "active=true",
                "request_headers": {"Accept": "application/json", "Authorization": "Bearer eyJ0..."},
                "request_body": None,
                "status": 200,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": json.dumps({
                    "coupons": [
                        {"code": "SUMMER20", "discount": 0.2, "type": "percent", "expires": "2026-08-31", "used": 4821},
                        {"code": "FREESHIP", "discount": 0.0, "type": "shipping", "expires": "2026-06-30", "used": 1203},
                        {"code": "NEWUSER10", "discount": 0.1, "type": "percent", "expires": "2026-12-31", "used": 8741},
                    ],
                    "total": 3,
                }),
                "elapsed_ms": 38.9,
                "timestamp": _ts(7, 10, 6),
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
                "timestamp": _ts(0.5, 8, 55),
                "method": "POST",
                "url": "https://api.shop.example.com/v2/auth/login",
                "request_headers": {"Content-Type": "application/json", "Origin": "https://shop.example.com"},
                "request_body": '{"email":"alice@example.com","password":"[REDACTED]"}',
                "status_code": 200,
                "response_headers": {"Content-Type": "application/json", "Set-Cookie": "session=abc; HttpOnly; Secure"},
                "response_body": '{"access_token":"eyJ0...","refresh_token":"rt_demo_001","expires_in":3600}',
                "elapsed_ms": 134.2,
                "state": "forwarded",
                "flags": [],
                "error": None,
            },
            {
                "flow_id": "flow-demo-0002-4000-8000-000000000002",
                "timestamp": _ts(0.5, 9, 0),
                "method": "GET",
                "url": "https://api.shop.example.com/v2/users?page=1&limit=20",
                "request_headers": {"Accept": "application/json", "X-API-Key": "sk_test_demo_key_12345"},
                "request_body": None,
                "status_code": 200,
                "response_headers": {"Content-Type": "application/json", "X-Request-Id": "req_abc001", "X-RateLimit-Remaining": "58"},
                "response_body": '{"success":true,"data":[{"id":"usr_001","email":"alice@example.com"},{"id":"usr_002","email":"bob@example.com"}],"total":143}',
                "elapsed_ms": 91.6,
                "state": "forwarded",
                "flags": [
                    {
                        "type": "missing_header",
                        "severity": "low",
                        "location": "response_headers",
                        "detail": "Missing Content-Security-Policy header",
                    },
                ],
                "error": None,
            },
            {
                "flow_id": "flow-demo-0003-4000-8000-000000000003",
                "timestamp": _ts(0.5, 9, 2),
                "method": "GET",
                "url": "https://api.shop.example.com/v2/products?category=electronics&in_stock=true",
                "request_headers": {"Accept": "application/json"},
                "request_body": None,
                "status_code": 200,
                "response_headers": {"Content-Type": "application/json", "Cache-Control": "max-age=60", "ETag": '"v2.5.0-prod-42"'},
                "response_body": '{"success":true,"data":[{"sku":"ELEC-001","name":"Wireless Mouse","price":44.99}],"total":18}',
                "elapsed_ms": 62.1,
                "state": "forwarded",
                "flags": [],
                "error": None,
            },
            {
                "flow_id": "flow-demo-0004-4000-8000-000000000004",
                "timestamp": _ts(0.5, 9, 5),
                "method": "POST",
                "url": "https://api.shop.example.com/v2/orders",
                "request_headers": {"Content-Type": "application/json", "Authorization": "Bearer sk_test_demo_key_12345"},
                "request_body": '{"user_id":"usr_001","items":[{"sku":"ELEC-001","qty":2,"unit_price":44.99},{"sku":"ELEC-002","qty":1,"unit_price":129.00}]}',
                "status_code": 201,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": '{"order_id":"ord_demo_042","status":"pending","total":218.98}',
                "elapsed_ms": 298.7,
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
                "flow_id": "flow-demo-0005-4000-8000-000000000005",
                "timestamp": _ts(0.5, 9, 8),
                "method": "GET",
                "url": "https://api.shop.example.com/v2/orders/ord_demo_042",
                "request_headers": {"Accept": "application/json", "Authorization": "Bearer sk_test_demo_key_12345"},
                "request_body": None,
                "status_code": 200,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": '{"order_id":"ord_demo_042","status":"processing","items":[{"sku":"ELEC-001","qty":2},{"sku":"ELEC-002","qty":1}],"tracking":null}',
                "elapsed_ms": 58.3,
                "state": "forwarded",
                "flags": [],
                "error": None,
            },
            {
                "flow_id": "flow-demo-0006-4000-8000-000000000006",
                "timestamp": _ts(0.4, 9, 12),
                "method": "GET",
                "url": "https://api.shop.example.com/v2/products/ELEC-999",
                "request_headers": {"Accept": "application/json"},
                "request_body": None,
                "status_code": 404,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": '{"error":"product_not_found","message":"Product ELEC-999 not found or discontinued"}',
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
                "flow_id": "flow-demo-0007-4000-8000-000000000007",
                "timestamp": _ts(0.4, 9, 15),
                "method": "POST",
                "url": "https://api.shop.example.com/v2/orders",
                "request_headers": {"Content-Type": "application/json"},
                "request_body": '{"user_id":"usr_001","items":[]}',
                "status_code": 422,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": '{"error":"validation_failed","message":"items must not be empty","field":"items"}',
                "elapsed_ms": 31.7,
                "state": "forwarded",
                "flags": [
                    {
                        "type": "validation_error_leaked",
                        "severity": "info",
                        "location": "response_body",
                        "detail": "422 response body exposes internal field name 'items' — consider a generic error schema",
                    },
                ],
                "error": None,
            },
            {
                "flow_id": "flow-demo-0008-4000-8000-000000000008",
                "timestamp": _ts(0.3, 9, 20),
                "method": "POST",
                "url": "https://api.github.com/graphql",
                "request_headers": {"Content-Type": "application/json", "Authorization": "bearer ghp_demo_token"},
                "request_body": '{"query":"query { viewer { login name followers { totalCount } } }"}',
                "status_code": 200,
                "response_headers": {"Content-Type": "application/json", "X-RateLimit-Remaining": "4982"},
                "response_body": '{"data":{"viewer":{"login":"alice-dev","name":"Alice Smith","followers":{"totalCount":318}}}}',
                "elapsed_ms": 185.9,
                "state": "forwarded",
                "flags": [],
                "error": None,
            },
            {
                "flow_id": "flow-demo-0009-4000-8000-000000000009",
                "timestamp": _ts(0.3, 9, 25),
                "method": "POST",
                "url": "https://users.internal.example.com:50051",
                "request_headers": {"content-type": "application/grpc+json"},
                "request_body": '{"_grpc_method":"user.UserService/GetUser","user_id":"usr_7f4a1b2c"}',
                "status_code": 200,
                "response_headers": {"content-type": "application/grpc+json", "grpc-status": "0"},
                "response_body": '{"user_id":"usr_7f4a1b2c","display_name":"Bob Marley","email":"bob@example.com"}',
                "elapsed_ms": 18.3,
                "state": "forwarded",
                "flags": [],
                "error": None,
            },
            {
                "flow_id": "flow-demo-0010-4000-8000-000000000010",
                "timestamp": _ts(0.2, 9, 30),
                "method": "GET",
                "url": "https://api.shop.example.com/v2/users?search=' OR '1'='1",
                "request_headers": {"Accept": "application/json"},
                "request_body": None,
                "status_code": 200,
                "response_headers": {"Content-Type": "application/json", "X-Debug-Query": "SELECT * FROM users WHERE name LIKE '''%' OR '1'='1%'''"},
                "response_body": '{"success":true,"data":[{"id":"usr_001"},{"id":"usr_002"},{"id":"usr_003"}],"total":143}',
                "elapsed_ms": 312.4,
                "state": "forwarded",
                "flags": [
                    {
                        "type": "sql_injection_suspected",
                        "severity": "critical",
                        "location": "request_url",
                        "detail": "SQL injection payload detected in query parameter 'search'; response returned full user table",
                    },
                    {
                        "type": "sensitive_header_leaked",
                        "severity": "high",
                        "location": "response_headers",
                        "detail": "X-Debug-Query header exposes raw SQL query in production response",
                    },
                ],
                "error": None,
            },
            {
                "flow_id": "flow-demo-0011-4000-8000-000000000011",
                "timestamp": _ts(0.15, 9, 35),
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
            {
                "flow_id": "flow-demo-0012-4000-8000-000000000012",
                "timestamp": _ts(0.08, 9, 45),
                "method": "GET",
                "url": "https://api.shop.example.com/v2/health",
                "request_headers": {"Accept": "application/json"},
                "request_body": None,
                "status_code": 200,
                "response_headers": {"Content-Type": "application/json"},
                "response_body": '{"status":"ok","version":"2.5.0","db":"connected","redis":"connected","uptime_s":918432}',
                "elapsed_ms": 13.8,
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
            "last_triggered": _ts(0.5, 9, 0),
            "last_status": 200,
        },
        {
            "id": "wh000002",
            "collection_id": _COL_GRAPHQL_ID,
            "environment_id": _ENV_LOCAL_ID,
            "url": "https://hooks.example.com/theridion/graphql-smoke",
            "enabled": False,
            "last_triggered": _ts(3, 14, 0),
            "last_status": 200,
        },
        {
            "id": "wh000003",
            "collection_id": _COL_REST_ID,
            "environment_id": _ENV_PRODUCTION_ID,
            "url": "https://hooks.slack.com/services/T000/B000/demo_slack_webhook",
            "enabled": True,
            "last_triggered": _ts(1, 9, 0),
            "last_status": 200,
        },
        {
            "id": "wh000004",
            "collection_id": _COL_GRPC_ID,
            "environment_id": _ENV_STAGING_ID,
            "url": "https://hooks.example.com/theridion/grpc-health",
            "enabled": True,
            "last_triggered": _ts(0.5, 11, 0),
            "last_status": 200,
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
