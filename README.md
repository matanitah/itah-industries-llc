# Itah Industries LLC

Personal AWS control plane + DGX Spark data plane for customer AI APIs, plus a unified **website + customer portal** (Next.js).

**Architecture:** outbound Cloudflare Tunnel (**1A**) + hybrid edge (**2C**) — AWS owns keys/scopes/online flag; Spark owns GPU workloads; `website/` serves portfolio + username/password portal. See [ARCHITECTURE.md](ARCHITECTURE.md).

```text
Browser  → website (marketing + /login + /app)
              └─ BFF  → API Gateway + authorizer → Tunnel → spark-gateway → Ollama/Docling

API keys → API Gateway (programmatic clients; unchanged)

Admin    → spark-gateway /admin (localhost) — online flag, keys, portal users
```

## Layout

| Path | Role |
|------|------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Solution architecture |
| [`infra/`](infra/) | Terraform: API Gateway, DynamoDB, authorizer, IAM |
| [`spark/`](spark/) | uv + FastAPI gateway, admin UI, tunnel scripts |
| [`website/`](website/) | Next.js: portfolio + customer login + chat/docs portal |

## Quick start

### 1. Control plane (AWS)

New resources (portal users table, portal authorizer token) are in Terraform code. Apply when you are ready — **this integration phase did not apply changes**.

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# set spark_origin_base_url, edge_shared_token, portal_shared_token
terraform init && terraform plan   # review first
# terraform apply                  # only when you choose
```

### 2. Data plane (any Ollama host)

```bash
cd spark
cp .env.example .env
uv sync
./scripts/run-gateway.sh
# Admin: http://127.0.0.1:8080/admin/
```

### 3. Website + portal (local)

```bash
cd website
cp .env.example .env.local
# PORTAL_SESSION_SECRET, PORTAL_EDGE_TOKEN (= portal_shared_token), ITAH_API_BASE_URL
npm install
npm run dev
# http://localhost:3000  — marketing
# http://localhost:3000/login — customer login
```

In Spark admin: create customer → grant scopes → **Invite** (email) or **Portal login**
(username/password) → Go online.

### 4. Programmatic API (keys still work)

```bash
curl -sS "$API_ENDPOINT/v1/llm/completions" \
  -H "Authorization: Bearer itah_..." \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}]}'
```

## Live hostnames

| Host | Backend | Always on? |
|------|---------|------------|
| `matanitah.com` / `www` | GitHub Pages (`personal-website-repo`) | Yes |
| `spark-origin.matanitah.com` | Mac tunnel → Next.js portal + spark-gateway `/v1` | Only while Mac + tunnel run |

Portal **capacity** badge follows the admin dashboard Go online/offline flag in
DynamoDB — not whether the personal site is up. See
[docs/GODADDY_DNS_CUTOVER.md](docs/GODADDY_DNS_CUTOVER.md).

Demo portal login: username `admin` (rotate password after demos).

## Defaults

- Region: `us-east-1`
- Tunnel: Cloudflare Tunnel
- Package/venv: `uv` under `spark/`; `npm` under `website/`
- LLM: host `OLLAMA_MODEL` (or first local model)
