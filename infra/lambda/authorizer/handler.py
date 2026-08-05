"""API Gateway HTTP API Lambda authorizer for Itah customer keys + portal BFF."""

from __future__ import annotations

import hashlib
import os
from typing import Any

import boto3

dynamodb = boto3.resource("dynamodb")
api_keys = dynamodb.Table(os.environ["API_KEYS_TABLE"])
customers = dynamodb.Table(os.environ["CUSTOMERS_TABLE"])
entitlements = dynamodb.Table(os.environ["ENTITLEMENTS_TABLE"])
spark_status = dynamodb.Table(os.environ["SPARK_STATUS_TABLE"])
PORTAL_SHARED_TOKEN = os.environ.get("PORTAL_SHARED_TOKEN", "")

ROUTE_SCOPES = {
    "GET /v1/health": "spark:health",
    "POST /v1/llm/completions": "llm:completions",
    "GET /v1/docling/health": "docling:health",
    "POST /v1/docling/convert": "docling:convert",
}

# Agent-spark routes don't use the scope/entitlement DynamoDB table above --
# entitlement for these is a separate concept (which agent-spark agent a
# customer may open, see customer_agents table) checked by spark-gateway
# itself (services/control_plane.customer_has_agent), not by this
# authorizer. This authorizer's job for these routes is only to confirm the
# request is a legitimate portal-BFF or API-key call for *some* known
# customer and that Spark is online -- so they need a route match here, but
# map to a scope that's a pure passthrough (always granted once the caller
# is authenticated), not a real per-customer DynamoDB entitlement lookup.
def _is_agent_route(route_key: str) -> bool:
    return route_key.endswith("/v1/agents") or "/v1/agents/" in route_key


def _header(headers: dict[str, str], name: str) -> str:
    lower = {k.lower(): v for k, v in headers.items()}
    return lower.get(name.lower(), "") or ""


def _extract_bearer(headers: dict[str, str]) -> str | None:
    auth = _header(headers, "authorization")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    key = _header(headers, "x-api-key")
    return key or None


def _deny(reason: str) -> dict[str, Any]:
    return {
        "isAuthorized": False,
        "context": {"reason": reason},
    }


def _allow(customer_id: str, scope: str) -> dict[str, Any]:
    return {
        "isAuthorized": True,
        "context": {
            "customer_id": customer_id,
            "scope": scope,
        },
    }


def _route_key(event: dict[str, Any]) -> str:
    route_key = event.get("routeKey") or ""
    if route_key and route_key != "$default":
        return route_key
    method = (event.get("requestContext") or {}).get("http", {}).get("method", "")
    path = (event.get("requestContext") or {}).get("http", {}).get("path", "")
    return f"{method} {path}"


def _resolve_scope(event: dict[str, Any]) -> str | None:
    route_key = _route_key(event)
    scope = ROUTE_SCOPES.get(route_key)
    if scope:
        return scope
    if _is_agent_route(route_key):
        return "agent:access"  # sentinel: authenticate + spark-online only, see _is_agent_route
    return None


def _check_customer_and_scope(customer_id: str, scope: str) -> dict[str, Any] | None:
    customer = customers.get_item(Key={"customer_id": customer_id}).get("Item")
    if not customer or not customer.get("enabled"):
        return _deny("customer_disabled")
    if scope == "agent:access":
        # Agent-spark entitlement is per-agent-slug (customer_agents table),
        # not a generic scope -- spark-gateway checks it itself
        # (control_plane.customer_has_agent) once the request reaches it.
        # This authorizer only needs to confirm the customer is real/enabled.
        return None
    entitlement = entitlements.get_item(
        Key={"customer_id": customer_id, "scope": scope}
    ).get("Item")
    if not entitlement or not entitlement.get("enabled"):
        return _deny("scope_denied")
    return None


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    headers = event.get("headers") or {}
    scope = _resolve_scope(event)
    if not scope:
        return _deny("unknown_route")

    status = spark_status.get_item(Key={"id": "singleton"}).get("Item") or {}
    if not status.get("online"):
        return _deny("spark_offline")

    portal_token = _header(headers, "x-itah-portal-token")
    customer_id_header = _header(headers, "x-itah-customer-id").strip()
    if PORTAL_SHARED_TOKEN and portal_token and portal_token == PORTAL_SHARED_TOKEN:
        if not customer_id_header:
            return _deny("missing_customer_id")
        denied = _check_customer_and_scope(customer_id_header, scope)
        if denied:
            return denied
        return _allow(customer_id=customer_id_header, scope=scope)

    raw_key = _extract_bearer(headers)
    if not raw_key:
        return _deny("missing_api_key")

    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    key_item = api_keys.get_item(Key={"key_hash": key_hash}).get("Item")
    if not key_item or not key_item.get("enabled"):
        return _deny("invalid_key")

    customer_id = key_item["customer_id"]
    denied = _check_customer_and_scope(customer_id, scope)
    if denied:
        return denied

    return _allow(customer_id=customer_id, scope=scope)
