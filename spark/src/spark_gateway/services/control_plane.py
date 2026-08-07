"""DynamoDB control-plane client for the Spark administrator dashboard."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from argon2 import PasswordHasher
from botocore.exceptions import BotoCoreError, ClientError

from spark_gateway.config import Settings

SCOPES = (
    "spark:health",
    "llm:completions",
    "docling:convert",
    "docling:health",
)

# agent-spark agents customers can be entitled to. Keep in sync with the
# directory names under agent-spark/agents/ (services/agents.py validates
# against the actual filesystem at request time; this list is just what the
# admin UI offers to grant).
AGENT_SLUGS = (
    "cigna-mtsinai-negotiation",
    "animal-rights-watch",
    "cigna-actuarial-agent",
)

_ph = PasswordHasher()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return f"itah_{secrets.token_urlsafe(32)}"


def hash_invite_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)


def _public_invite(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "token_hash": raw.get("token_hash"),
        "email": raw.get("email"),
        "customer_id": raw.get("customer_id"),
        "status": raw.get("status", "pending"),
        "expires_at": raw.get("expires_at"),
        "created_at": raw.get("created_at"),
        "used_at": raw.get("used_at"),
        "email_sent": bool(raw.get("email_sent", False)),
    }


def _public_portal_user(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": raw.get("username"),
        "customer_id": raw.get("customer_id"),
        "enabled": bool(raw.get("enabled", True)),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
    }


def _public_api_key(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "key_hash": raw.get("key_hash"),
        "key_prefix": raw.get("key_prefix"),
        "customer_id": raw.get("customer_id"),
        "label": raw.get("label"),
        "enabled": bool(raw.get("enabled", True)),
        "created_at": raw.get("created_at"),
    }


class ControlPlane:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._dynamo = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.customers = self._dynamo.Table(settings.dynamodb_customers_table)
        self.api_keys = self._dynamo.Table(settings.dynamodb_api_keys_table)
        self.entitlements = self._dynamo.Table(settings.dynamodb_entitlements_table)
        self.spark_status = self._dynamo.Table(settings.dynamodb_spark_status_table)
        self.portal_users = self._dynamo.Table(settings.dynamodb_portal_users_table)
        self.portal_invites = self._dynamo.Table(settings.dynamodb_portal_invites_table)
        self.customer_agents = self._dynamo.Table(settings.dynamodb_customer_agents_table)
        self._ses = boto3.client("ses", region_name=settings.aws_region)

    # --- Spark capacity -------------------------------------------------

    def get_spark_status(self) -> dict[str, Any]:
        try:
            item = self.spark_status.get_item(Key={"id": "singleton"}).get("Item")
            return item or {"id": "singleton", "online": False}
        except (ClientError, BotoCoreError) as exc:
            return {"id": "singleton", "online": False, "error": str(exc)}

    def set_spark_online(self, online: bool, origin_base_url: str = "") -> dict[str, Any]:
        item = {
            "id": "singleton",
            "online": online,
            "origin_base_url": origin_base_url if online else "",
            "updated_at": _utcnow(),
            "updated_by": "spark-admin",
        }
        self.spark_status.put_item(Item=item)
        return item

    # --- Customers ------------------------------------------------------

    def list_customers(self) -> list[dict[str, Any]]:
        items = self.customers.scan().get("Items", [])
        return sorted(items, key=lambda c: str(c.get("customer_id", "")))

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        return self.customers.get_item(Key={"customer_id": customer_id}).get("Item")

    def upsert_customer(self, customer_id: str, name: str, enabled: bool = True) -> dict[str, Any]:
        customer_id = customer_id.strip()
        existing = self.get_customer(customer_id) or {}
        item = {
            "customer_id": customer_id,
            "name": name.strip(),
            "enabled": enabled,
            "created_at": existing.get("created_at") or _utcnow(),
            "updated_at": _utcnow(),
        }
        self.customers.put_item(Item=item)
        return item

    def set_customer_enabled(self, customer_id: str, enabled: bool) -> None:
        self.customers.update_item(
            Key={"customer_id": customer_id.strip()},
            UpdateExpression="SET enabled = :e, updated_at = :u",
            ExpressionAttributeValues={":e": enabled, ":u": _utcnow()},
        )

    def delete_customer(self, customer_id: str, *, cascade: bool = True) -> None:
        customer_id = customer_id.strip()
        if cascade:
            for ent in self.list_entitlements(customer_id):
                self.delete_entitlement(customer_id, str(ent["scope"]))
            for key in self.list_api_keys(customer_id=customer_id):
                self.delete_api_key(str(key["key_hash"]))
            for user in self.list_portal_users(customer_id=customer_id):
                self.delete_portal_user(str(user["username"]))
            for agent in self.list_customer_agents(customer_id):
                self.delete_customer_agent(customer_id, str(agent["agent_slug"]))
        self.customers.delete_item(Key={"customer_id": customer_id})

    # --- Entitlements ---------------------------------------------------

    def set_entitlement(self, customer_id: str, scope: str, enabled: bool) -> dict[str, Any]:
        if scope not in SCOPES:
            raise ValueError(f"Unknown scope: {scope}")
        item = {
            "customer_id": customer_id.strip(),
            "scope": scope,
            "enabled": enabled,
            "updated_at": _utcnow(),
        }
        self.entitlements.put_item(Item=item)
        return item

    def list_entitlements(self, customer_id: str | None = None) -> list[dict[str, Any]]:
        if customer_id:
            result = self.entitlements.query(
                KeyConditionExpression="customer_id = :cid",
                ExpressionAttributeValues={":cid": customer_id.strip()},
            )
            return result.get("Items", [])
        items = self.entitlements.scan().get("Items", [])
        return sorted(
            items,
            key=lambda e: (str(e.get("customer_id", "")), str(e.get("scope", ""))),
        )

    def delete_entitlement(self, customer_id: str, scope: str) -> None:
        self.entitlements.delete_item(
            Key={"customer_id": customer_id.strip(), "scope": scope.strip()}
        )

    def grant_all_scopes(self, customer_id: str, enabled: bool = True) -> None:
        for scope in SCOPES:
            self.set_entitlement(customer_id, scope, enabled)

    def revoke_all_scopes(self, customer_id: str) -> None:
        for ent in self.list_entitlements(customer_id):
            self.delete_entitlement(customer_id, str(ent["scope"]))

    # --- Agent-spark agent entitlements ----------------------------------

    def set_customer_agent(self, customer_id: str, agent_slug: str, enabled: bool) -> dict[str, Any]:
        if agent_slug not in AGENT_SLUGS:
            raise ValueError(f"Unknown agent_slug: {agent_slug}")
        item = {
            "customer_id": customer_id.strip(),
            "agent_slug": agent_slug.strip(),
            "enabled": enabled,
            "updated_at": _utcnow(),
        }
        self.customer_agents.put_item(Item=item)
        return item

    def list_customer_agents(self, customer_id: str | None = None) -> list[dict[str, Any]]:
        if customer_id:
            result = self.customer_agents.query(
                KeyConditionExpression="customer_id = :cid",
                ExpressionAttributeValues={":cid": customer_id.strip()},
            )
            return result.get("Items", [])
        items = self.customer_agents.scan().get("Items", [])
        return sorted(items, key=lambda a: (str(a.get("customer_id", "")), str(a.get("agent_slug", ""))))

    def customer_has_agent(self, customer_id: str, agent_slug: str) -> bool:
        item = self.customer_agents.get_item(
            Key={"customer_id": customer_id.strip(), "agent_slug": agent_slug.strip()}
        ).get("Item")
        return bool(item and item.get("enabled", True))

    def delete_customer_agent(self, customer_id: str, agent_slug: str) -> None:
        self.customer_agents.delete_item(
            Key={"customer_id": customer_id.strip(), "agent_slug": agent_slug.strip()}
        )

    # --- API keys -------------------------------------------------------

    def create_api_key(self, customer_id: str, label: str = "") -> tuple[str, dict[str, Any]]:
        raw = generate_api_key()
        key_hash = hash_api_key(raw)
        item = {
            "key_hash": key_hash,
            "customer_id": customer_id.strip(),
            "key_prefix": raw[:12],
            "label": label.strip() or "default",
            "enabled": True,
            "created_at": _utcnow(),
        }
        self.api_keys.put_item(Item=item)
        return raw, item

    def list_api_keys(self, customer_id: str | None = None) -> list[dict[str, Any]]:
        if customer_id:
            result = self.api_keys.query(
                IndexName="customer_id-index",
                KeyConditionExpression="customer_id = :cid",
                ExpressionAttributeValues={":cid": customer_id.strip()},
            )
            items = result.get("Items", [])
        else:
            items = self.api_keys.scan().get("Items", [])
        return [_public_api_key(i) for i in sorted(items, key=lambda k: str(k.get("created_at", "")), reverse=True)]

    def set_api_key_enabled(self, key_hash: str, enabled: bool) -> None:
        self.api_keys.update_item(
            Key={"key_hash": key_hash.strip()},
            UpdateExpression="SET enabled = :e",
            ExpressionAttributeValues={":e": enabled},
        )

    def disable_api_key(self, key_hash: str) -> None:
        self.set_api_key_enabled(key_hash, False)

    def delete_api_key(self, key_hash: str) -> None:
        self.api_keys.delete_item(Key={"key_hash": key_hash.strip()})

    # --- Portal users ---------------------------------------------------

    def upsert_portal_user(
        self,
        username: str,
        customer_id: str,
        password: str,
        enabled: bool = True,
    ) -> dict[str, Any]:
        username = username.strip()
        customer_id = customer_id.strip()
        if not username or not customer_id or not password:
            raise ValueError("username, customer_id, and password are required")
        existing = self.portal_users.get_item(Key={"username": username}).get("Item") or {}
        item = {
            "username": username,
            "customer_id": customer_id,
            "password_hash": _ph.hash(password),
            "enabled": enabled,
            "created_at": existing.get("created_at") or _utcnow(),
            "updated_at": _utcnow(),
        }
        self.portal_users.put_item(Item=item)
        return _public_portal_user(item)

    def list_portal_users(self, customer_id: str | None = None) -> list[dict[str, Any]]:
        if customer_id:
            result = self.portal_users.query(
                IndexName="customer_id-index",
                KeyConditionExpression="customer_id = :cid",
                ExpressionAttributeValues={":cid": customer_id.strip()},
            )
            items = result.get("Items", [])
        else:
            items = self.portal_users.scan().get("Items", [])
        return [
            _public_portal_user(i)
            for i in sorted(items, key=lambda u: str(u.get("username", "")))
        ]

    def list_portal_users_for_customer(self, customer_id: str) -> list[dict[str, Any]]:
        return self.list_portal_users(customer_id=customer_id)

    def set_portal_user_enabled(self, username: str, enabled: bool) -> None:
        self.portal_users.update_item(
            Key={"username": username.strip()},
            UpdateExpression="SET enabled = :e, updated_at = :u",
            ExpressionAttributeValues={":e": enabled, ":u": _utcnow()},
        )

    def reassign_portal_user(self, username: str, customer_id: str) -> None:
        self.portal_users.update_item(
            Key={"username": username.strip()},
            UpdateExpression="SET customer_id = :c, updated_at = :u",
            ExpressionAttributeValues={":c": customer_id.strip(), ":u": _utcnow()},
        )

    def delete_portal_user(self, username: str) -> None:
        self.portal_users.delete_item(Key={"username": username.strip()})

    # --- Portal invites (24h signup links) ------------------------------

    def create_portal_invite(self, email: str, customer_id: str) -> dict[str, Any]:
        email = email.strip().lower()
        customer_id = customer_id.strip()
        if not email or "@" not in email or not customer_id:
            raise ValueError("valid email and customer_id are required")

        customer = self.customers.get_item(Key={"customer_id": customer_id}).get("Item")
        if not customer:
            raise ValueError(f"unknown customer_id: {customer_id}")
        if customer.get("enabled") is False:
            raise ValueError(f"customer {customer_id} is disabled")

        # Revoke prior pending invites for this email.
        for prior in self.list_portal_invites(email=email):
            if prior.get("status") == "pending":
                self.revoke_portal_invite(str(prior["token_hash"]))

        raw_token = generate_invite_token()
        token_hash = hash_invite_token(raw_token)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=24)
        base = self.settings.portal_public_base_url.rstrip("/")
        invite_url = f"{base}/invite/{raw_token}"

        item = {
            "token_hash": token_hash,
            "email": email,
            "customer_id": customer_id,
            "status": "pending",
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "expires_epoch": int(expires.timestamp()),
            "email_sent": False,
            "created_by": "spark-admin",
        }

        email_error = ""
        from_addr = (self.settings.invite_from_email or "").strip()
        if from_addr:
            try:
                self._ses.send_email(
                    Source=from_addr,
                    Destination={"ToAddresses": [email]},
                    Message={
                        "Subject": {"Data": "Your Itah Industries portal invite"},
                        "Body": {
                            "Text": {
                                "Data": (
                                    "You have been invited to create an Itah Industries portal account.\n\n"
                                    f"Open this link within 24 hours:\n{invite_url}\n\n"
                                    "If you did not expect this, ignore this email."
                                )
                            }
                        },
                    },
                )
                item["email_sent"] = True
            except (BotoCoreError, ClientError) as exc:
                email_error = str(exc)

        self.portal_invites.put_item(Item=item)
        return {
            **_public_invite(item),
            "invite_url": invite_url,
            "raw_token": raw_token,
            "email_error": email_error,
        }

    def list_portal_invites(self, email: str | None = None) -> list[dict[str, Any]]:
        if email:
            result = self.portal_invites.query(
                IndexName="email-index",
                KeyConditionExpression="email = :e",
                ExpressionAttributeValues={":e": email.strip().lower()},
            )
            items = result.get("Items", [])
        else:
            items = self.portal_invites.scan().get("Items", [])
        return [
            _public_invite(i)
            for i in sorted(items, key=lambda x: str(x.get("created_at", "")), reverse=True)
        ]

    def revoke_portal_invite(self, token_hash: str) -> None:
        self.portal_invites.update_item(
            Key={"token_hash": token_hash.strip()},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "revoked"},
        )

    # --- Dashboard aggregate --------------------------------------------

    def dashboard_snapshot(self) -> dict[str, Any]:
        customers = self.list_customers()
        entitlements = self.list_entitlements()
        api_keys = self.list_api_keys()
        portal_users = self.list_portal_users()
        portal_invites = self.list_portal_invites()
        customer_agents = self.list_customer_agents()

        def _blank() -> dict[str, Any]:
            return {"entitlements": [], "api_keys": [], "portal_users": [], "agents": []}

        by_customer: dict[str, dict[str, Any]] = {}
        for c in customers:
            cid = str(c["customer_id"])
            by_customer[cid] = {"customer": c, **_blank()}

        def _bucket(cid: str) -> dict[str, Any]:
            return by_customer.setdefault(
                cid, {"customer": {"customer_id": cid, "name": "?", "enabled": False}, **_blank()}
            )

        for e in entitlements:
            _bucket(str(e.get("customer_id", "")))["entitlements"].append(e)
        for k in api_keys:
            _bucket(str(k.get("customer_id", "")))["api_keys"].append(k)
        for u in portal_users:
            _bucket(str(u.get("customer_id", "")))["portal_users"].append(u)
        for a in customer_agents:
            _bucket(str(a.get("customer_id", "")))["agents"].append(a)

        return {
            "status": self.get_spark_status(),
            "customers": customers,
            "entitlements": entitlements,
            "api_keys": api_keys,
            "portal_users": portal_users,
            "portal_invites": portal_invites,
            "customer_agents": customer_agents,
            "by_customer": by_customer,
            "scopes": SCOPES,
            "agent_slugs": AGENT_SLUGS,
        }
