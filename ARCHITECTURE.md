# Solution Architecture — Itah Industries LLC

**Decisions locked in:** outbound tunnel from DGX Spark (**1A**) + hybrid control plane (**2C**).

| Default | Choice |
|---------|--------|
| Region | `us-east-1` |
| Tunnel | Cloudflare Tunnel (`cloudflared` on Spark) |
| Customer edge | Amazon API Gateway (HTTP API) |
| Auth / entitlements | API keys in DynamoDB + Lambda authorizer; portal username/password (argon2) + BFF portal token |
| Spark runtime | Python via `uv`, FastAPI, local Ollama (any model via `OLLAMA_MODEL`), Docling |
| Admin UI | FastAPI + Jinja templates on Spark (private; not a public customer surface) |
| Public site + portal | Next.js in `website/` — portfolio + `/login` + `/app` (chat + Docling) |

---

## 1. Goals

1. Manage the Itah Industries AWS account as the durable control plane (customers, keys, scopes, online/offline).
2. Use the DGX Spark as on-demand GPU compute (Ollama + Docling), reachable by customers only when you turn it on.
3. Keep the administrator dashboard reachable only from the Spark (or via the tunnel with an identity gate), never as a public customer API.
4. Ship reusable Terraform + Spark patterns so new APIs are mostly “register route + scope + backend.”
5. Let customers sign in with username/password on the public website and use chat + Docling in a portal (API keys remain for programmatic access).

---

## 1b. Website + portal (browser path)

```text
Browser → matanitah.com          GitHub Pages (always on; personal portfolio)
Browser → spark-origin…/login    Next.js portal on Mac (tunnel)
            /app/chat|docs       session cookie → BFF
                                 BFF adds X-Itah-Portal-Token + X-Itah-Customer-Id
                              → API Gateway authorizer → Spark (when admin online)
```

`matanitah.com` stays on GitHub Pages and does not depend on the Mac tunnel.
Capacity online/offline is the DynamoDB `spark_status` flag set from the Spark admin UI.

---

## 2. High-level topology

```text
                         ┌──────────────────────────────────────┐
  Portal BFF / API keys  │              AWS (always on)         │
       │                 │  API Gateway HTTP API                │
       │                 │    · Lambda authorizer               │
       ▼                 │      (API key OR portal token)       │
  api edge ─────────────►│    · routes /v1/*                    │
                         │    · HTTP proxy → tunnel origin      │
                         │                                      │
                         │  DynamoDB                            │
                         │    customers | api_keys | entitlements│
                         │    spark_status | portal_users       │
                         │                                      │
                         │  IAM roles for Spark admin agent     │
                         └──────────────────┬───────────────────┘
                                            │
                     HTTPS to tunnel hostname (secret to edge)
                                            │
                         ┌──────────────────▼───────────────────┐
                         │     Cloudflare Tunnel (outbound)     │
                         │     Spark dials out; no inbound NAT  │
                         └──────────────────┬───────────────────┘
                                            │
                         ┌──────────────────▼───────────────────┐
                         │           DGX Spark (on demand)      │
                         │  spark-gateway + Ollama + Docling    │
                         │  /admin (portal user provisioning)   │
                         └──────────────────────────────────────┘
```

**Control plane (AWS):** identity of customers, which APIs exist, which keys may call them, whether Spark is accepting traffic.

**Data plane (Spark):** model inference and document processing. No customer master data required on the box beyond runtime config.

---

## 3. “Spark online” control flow

Turning Spark on is an **admin action**, not a customer action.

```text
Admin on Spark
  │
  ├─1─ Start local services (Ollama, Docling, spark-gateway)
  ├─2─ Start cloudflared (outbound tunnel)
  ├─3─ PUT spark_status = { online: true, origin: "...", updated_at }
  │      via admin agent (boto3 → DynamoDB) using scoped IAM
  └─4─ API Gateway integrations begin succeeding health checks

Admin turns off
  │
  ├─1─ PUT spark_status.online = false
  ├─2─ Authorizer rejects (or proxy returns 503) for customer routes
  └─3─ Stop cloudflared (and optionally local services)
```

**Customer experience when offline:** stable hostname on API Gateway returns `503 Spark offline` (or `403` if you prefer not to advertise capacity). DNS never flaps.

**Admin experience:** dashboard at `http://127.0.0.1:8080/admin` on the Spark (default). Optional later: Cloudflare Access on an `admin.` hostname restricted to your identity — still not a customer path.

---

## 4. Request path (customer LLM call)

```text
1. Customer  POST https://api.<domain>/v1/llm/completions
             Header: Authorization: Bearer <api_key>

2. API Gateway  →  Lambda authorizer
             · hash lookup of key in DynamoDB
             · key active? customer active?
             · scope `llm:completions` granted?
             · spark_status.online == true?
             · API entitlement enabled for this customer?

3. If allow → HTTP proxy to Cloudflare Tunnel origin
             POST https://<tunnel-origin>/v1/llm/completions
             (strip customer key; inject internal hop header/HMAC optional)

4. spark-gateway  →  Ollama  /api/chat  (model=gpt-oss:20b)

5. Response flows back unchanged in shape (OpenAI-ish JSON in v1)
```

Docling and health follow the same pattern with different scopes (`docling:convert`, `spark:health`).

---

## 4b. Agent-spark agents (long-running crawl agent + Streamlit dashboard)

`agent-spark/` hosts long-running research agents (e.g. `cigna-mtsinai-negotiation`,
`animal-rights-watch`): each crawls the web on a schedule, extracts facts via a
local LLM, scores/ranks entities, and maintains a markdown wiki — controlled
through a Streamlit dashboard. See `agent-spark/README.md` and
`agent-spark/core/README.md` for the full pattern.

**Shared instance, per-customer entitlement.** Each agent runs exactly **one**
process/DB/wiki, shared by every customer entitled to it — not one per
customer. If customer A and customer B are both entitled to
`cigna-mtsinai-negotiation`, they see the same dashboard, the same crawl
progress, the same wiki, and the same Start/Stop control (stopping it stops
it for both). What's per-customer is the *entitlement* — whether a given
customer may open/start/stop a given agent at all — tracked in DynamoDB's
`customer_agents` table, not the underlying data.

Two request paths, because Streamlit's live UI depends on a WebSocket and
API Gateway's HTTP API can't proxy WebSocket frames end to end:

```text
Start/stop + entitlement check (through API Gateway, like /v1/llm):
  Portal  /app/agents/[slug]  → BFF /api/agents/[slug]/start
    → edgeFetch (portal token + customer id) → API Gateway → spark-gateway
    → /v1/agents/{slug}/start → customer_agents entitlement check
    → agent_spark_core.procmgr.start(...) on the agent's one shared instance

Dashboard iframe (direct tunnel, bypasses API Gateway for the WebSocket):
  Portal  /app/agents/[slug]  → BFF /api/agents/[slug]/dashboard-url
    → spark-gateway /v1/agents/{slug}/dashboard-url (entitlement-checked)
    → ensures the agent's one shared Streamlit process is running on its
      declared port, mints a short-lived signed token, returns a tunnel-
      hostname URL
  Browser <iframe src="https://spark-origin.../agents/{slug}/?t=<token>">
    → Cloudflare Tunnel → spark-gateway re-checks the entitlement live (not
      just the token's validity, so a revoked entitlement takes effect
      immediately) → reverse-proxies HTTP *and* WebSocket to localhost:<port>
```

`customer_agents` (DynamoDB) is which agents a customer may open at all;
`agent-spark/agents/<slug>/agent.yaml` (on the Spark box) is where that
agent's one shared instance's wiki repo/port are declared. The admin grants
the former in `/admin`; the admin declares the latter once per agent (not
per customer).

---

## 5. Auth model

### 5.1 Customer API keys

| Property | Behavior |
|----------|----------|
| Format | `itah_` + high-entropy secret (shown once) |
| Storage | Only **key hash** (SHA-256) in DynamoDB; plaintext never stored |
| Binding | `customer_id` + list of scopes + `enabled` flag |
| Rotation | Create new key, disable old; no in-place secret update |
| Transport | `Authorization: Bearer` (preferred) or `X-Api-Key` |

### 5.2 Scopes (initial)

| Scope | Route |
|-------|--------|
| `spark:health` | `GET /v1/health` |
| `llm:completions` | `POST /v1/llm/completions` |
| `docling:convert` | `POST /v1/docling/convert` |
| `docling:health` | `GET /v1/docling/health` |

Admin can enable/disable a scope per customer without deleting keys.

### 5.3 Administrator

- No customer API key can call `/admin/*`.
- Admin routes bind to localhost on Spark by default.
- Admin mutates AWS state with an IAM role/user limited to: DynamoDB tables for keys/customers/status, and read of gateway config.
- Optional: shared secret between API Gateway and Spark (`X-Itah-Edge-Token`) so the tunnel origin rejects direct probes that bypass the edge.

---

## 6. Component design

### 6.1 `spark/` — DGX Spark data plane

| Process | Role |
|---------|------|
| **Ollama** | Serves the host’s configured model (`OLLAMA_MODEL`, or first local model if unset) |
| **Docling** | Document conversion HTTP service (container or local process) |
| **spark-gateway** | FastAPI app: public-ish `/v1/*` for the tunnel + `/admin/*` for you |
| **cloudflared** | Outbound tunnel; maps hostname → `localhost:8080` |

**uv** manages the gateway venv and lockfile. Scripts under `spark/scripts/` start/stop the stack and toggle online status.

### 6.2 `infra/` — AWS control plane (Terraform)

| Resource | Purpose |
|----------|---------|
| API Gateway HTTP API | Customer edge, custom domain later |
| Lambda authorizer | Key + scope + online checks |
| DynamoDB tables | Customers, keys, entitlements, spark_status |
| IAM role for Spark admin | Least-privilege writes from the box |
| (Optional) CloudWatch logs | Access / authorizer metrics |
| (Optional) ACM + Route53 | `api.<domain>` |

Terraform does **not** provision the DGX or Ollama. It provisions everything needed so that when the tunnel is up, customers can reach Spark safely.

### 6.3 Cloudflare Tunnel

- Created once in Cloudflare Zero Trust; credentials live on Spark (`~/.cloudflared` or `spark/secrets/`, gitignored).
- Ingress rule: `spark-origin.<your-tunnel>` → `http://127.0.0.1:8080`.
- API Gateway integration URI points at that origin (stored in SSM or Terraform variable — not committed if sensitive).
- Customers never receive the tunnel hostname; they only know `api.<domain>`.

---

## 7. Data model (DynamoDB)

**`customers`**

| PK | Attributes |
|----|------------|
| `customer_id` | `name`, `enabled`, `created_at` |

**`api_keys`**

| PK | Attributes |
|----|------------|
| `key_hash` | `customer_id`, `key_prefix`, `enabled`, `created_at`, `label` |

**`entitlements`**

| PK | SK | Attributes |
|----|----|------------|
| `customer_id` | `scope` | `enabled` |

**`spark_status`** (single-item table or PK=`singleton`)

| Attributes |
|------------|
| `online` (bool), `origin_base_url`, `updated_at`, `updated_by` |

**`portal_users`** (website login)

| PK | Attributes |
|----|------------|
| `username` | `customer_id`, `password_hash` (argon2), `enabled`, `created_at` |

GSI: `customer_id-index`.

**`customer_agents`** (agent-spark entitlements — see §4b)

| PK | SK | Attributes |
|----|----|------------|
| `customer_id` | `agent_slug` | `enabled`, `updated_at` |

---

## 8. Repository layout

```text
itah-industries-llc/
├── ARCHITECTURE.md
├── README.md
├── website/                 ← Next.js portfolio + portal (local; not deployed yet)
│   ├── app/(marketing)/
│   ├── app/login/
│   ├── app/app/             ← chat + docs + agents
│   └── app/api/             ← auth + BFF (incl. agents)
├── spark/                   ← DGX Spark / any Ollama host
│   ├── pyproject.toml
│   ├── src/spark_gateway/   ← routes/agents.py + services/agents.py
│   └── scripts/
├── agent-spark/             ← long-running crawl agents + Streamlit dashboards (§4b)
│   ├── core/                ← shared agent_spark_core pattern
│   └── agents/
│       ├── cigna-mtsinai-negotiation/
│       └── animal-rights-watch/
└── infra/                   ← Terraform AWS control plane
    ├── *.tf
    └── lambda/authorizer/
```

---

## 9. Security posture (v1)

- Spark has **no required inbound ports** on the LAN; only outbound HTTPS to Cloudflare.
- Customer API keys never stored plaintext; admin sees raw key **once** at creation.
- Portal passwords stored as argon2 hashes only; session JWT in httpOnly cookie.
- Portal BFF uses `PORTAL_EDGE_TOKEN` (never shipped to the browser).
- Admin UI not published on the customer API domain.
- Edge → origin hop can require a shared token.
- IAM for Spark is scoped to specific tables/actions.
- `AGENT_SPARK_GITHUB_TOKEN` (agent-spark wiki sync, §4b) is a fine-grained GitHub PAT scoped to the `itah-industries-wikis` org only, Contents: Read and write, nothing else — never a classic PAT with blanket `repo` access.
- Live `matanitah.com` Pages cutover is intentional and separate from this codebase phase.

---

## 10. Failure modes

| Condition | Customer sees | Operator action |
|-----------|---------------|-----------------|
| Spark offline flag | 503 / portal “Capacity offline” | Turn on in admin |
| Tunnel down, flag still online | 502/504 from gateway | Restart `cloudflared`; or auto-health later |
| Ollama down | 502 from spark-gateway health | Restart Ollama |
| Invalid/disabled key | 401/403 | Rotate or re-enable in admin |
| Bad portal password | 401 on `/login` | Reset via admin Portal login form |
| Scope missing | 403 | Grant entitlement |
| Agent not entitled | 403 on `/app/agents/[slug]` | Grant agent in admin `#agents` |
| Agent dashboard token expired/invalid | 403 from spark-gateway direct-tunnel path | Portal re-requests a fresh token each load; retry |
| No `agent.yaml` for an agent | 400 "no port declared" starting/opening the agent | Admin copies that agent's `agent.example.yaml` → `agent.yaml` on the Spark box |

---

## 11. Evolution path (out of scope for scaffold)

- Host `website/` and cut over DNS from GitHub Pages to the unified app.
- Move from Cloudflare origin proxy to **Tailscale + VPC connector** or **Client VPN (1B)** for enterprise private networking.
- Usage metering, per-customer quotas, billing exports.
- Multiple Spark nodes / model routing.
- Cloudflare Access in front of `/admin` for remote admin without localhost SSH.
- OpenAPI SDKs for customers.

---

## 12. Scaffold implementation map

| Piece | Location |
|-------|----------|
| FastAPI gateway + admin | `spark/src/spark_gateway/` |
| Ollama client (`OLLAMA_MODEL` / auto) | `spark/src/spark_gateway/services/ollama.py` |
| Docling client stub | `spark/src/spark_gateway/services/docling.py` |
| Portal user provisioning | `spark` admin + `control_plane.upsert_portal_user` |
| Tunnel / online scripts | `spark/scripts/` |
| API Gateway + DynamoDB + authorizer | `infra/` |
| Authorizer (API key + portal token) | `infra/lambda/authorizer/` |
| Marketing + portal Next.js app | `website/` |
| Agent-spark pattern (crawl loop + dashboard) | `agent-spark/core/` (see §4b) |
| Agent-spark agents | `agent-spark/agents/cigna-mtsinai-negotiation/`, `agent-spark/agents/animal-rights-watch/` |
| Agent entitlement + dashboard proxy (spark-gateway) | `spark/src/spark_gateway/routes/agents.py`, `services/agents.py` |
| Agent entitlement table (Terraform) | `infra/dynamodb.tf` (`customer_agents`) |
| Portal agents pages + BFF | `website/app/app/agents/`, `website/app/api/agents/` |