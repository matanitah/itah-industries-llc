# Spark data-plane gateway (DGX Spark)

Python FastAPI service that exposes:

- `GET /v1/health` — Spark + Ollama (+ Docling) health
- `POST /v1/llm/completions` — always `gpt-oss:20b` via local Ollama
- `GET /v1/docling/health` / `POST /v1/docling/convert`
- `/admin/*` — administrator dashboard (localhost)

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com) with at least one model pulled (any machine: Mac, DGX Spark, etc.)
- Docling HTTP service listening on `DOCLING_BASE_URL` (optional until you use Docling routes)
- AWS credentials that can write the DynamoDB control-plane tables
- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) for customer reachability

## Setup

```bash
cd spark
cp .env.example .env
# set OLLAMA_MODEL to a local model, e.g. llama3.2:latest or gpt-oss:20b
# leave OLLAMA_MODEL empty to auto-pick the first installed model
uv sync
```

## Run gateway

```bash
./scripts/run-gateway.sh
# Admin UI: http://127.0.0.1:8080/admin/
```

## Tunnel options

**Dev / Mac quick tunnel** (ephemeral `*.trycloudflare.com` URL — re-apply Terraform if it changes):

```bash
./scripts/dev-quick-tunnel.sh
```

**Named tunnel** (stable hostname for Spark/production):

```bash
cp secrets/cloudflared.yml.example secrets/cloudflared.yml
# edit tunnel UUID + credentials path
./scripts/run-tunnel.sh
```

Then set `spark_origin_base_url` in `infra/terraform.tfvars`, `terraform apply`, and use the admin UI **Go online**.

## Model policy

Completions use `OLLAMA_MODEL` from the host env (customers cannot select a model). On DGX Spark prefer `gpt-oss:20b`; on a Mac any local model works (e.g. `llama3.2:latest`).
