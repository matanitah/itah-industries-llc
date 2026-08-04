# matanitah.com DNS + host split

Keep the domain **registered at GoDaddy**. Point **nameservers** at Cloudflare.

```text
GoDaddy (registrar only)
   └── nameservers → Cloudflare DNS
                        ├── matanitah.com / www  → GitHub Pages (always on)
                        └── spark-origin…        → Tunnel → Mac
                                                   ├── :3000 portal UI
                                                   └── :8080 /v1/* (GPU)

API Gateway (AWS) ──HTTPS──► spark-origin.matanitah.com/v1/* ──► Mac :8080
```

**Capacity online/offline** is the admin dashboard DynamoDB flag (`itah-spark-status`),
not whether the personal site is reachable. `matanitah.com` never depends on the Mac.

## Step 1 — Cloudflare: add the site (get NS)

1. Open [Cloudflare Dashboard](https://dash.cloudflare.com/) → **Add a domain** → `matanitah.com`
2. Choose the **Free** plan
3. Copy the **two nameservers** Cloudflare shows

## Step 2 — GoDaddy: replace nameservers

1. GoDaddy → **My Products** → `matanitah.com` → **DNS** / **Nameservers**
2. Set **Custom** nameservers to Cloudflare’s two NS values
3. Wait until `dig +short matanitah.com NS` shows `*.ns.cloudflare.com`

## Step 3 — Always-on personal site (GitHub Pages)

Repo: `matanitahdev/personal-website-repo` (branch `main`, `CNAME` = `matanitah.com`).

Cloudflare DNS (DNS-only / grey cloud recommended for GitHub Pages SSL):

| Type | Name | Content |
|------|------|---------|
| CNAME | `@` (`matanitah.com`) | `matanitahdev.github.io` |
| CNAME | `www` | `matanitahdev.github.io` |

## Step 4 — Mac tunnel for spark-origin only

```bash
cloudflared tunnel login
cloudflared tunnel create itah-mac

cp spark/secrets/cloudflared.named.yml.example spark/secrets/cloudflared.named.yml
# fill tunnel UUID + credentials-file

cloudflared tunnel route dns itah-mac spark-origin.matanitah.com
# Do NOT route matanitah.com / www through the tunnel.
```

## Step 5 — Point AWS at the Spark origin

```bash
# infra/terraform.tfvars
spark_origin_base_url = "https://spark-origin.matanitah.com"

cd infra && terraform apply
```

Spark admin → **Go online** with `https://spark-origin.matanitah.com`.

## Step 6 — Run GPU / portal stack (Mac)

```bash
cd spark && ./scripts/run-gateway.sh          # :8080
cd website && npm run dev                     # :3000 (portal)
./spark/scripts/run-named-tunnel.sh           # spark-origin only
```

| Hostname | Serves | Depends on Mac? |
|----------|--------|-----------------|
| `matanitah.com` / `www` | Personal portfolio (GitHub Pages) | No |
| `spark-origin.matanitah.com` | Customer portal | Yes (tunnel) |
| `spark-origin.matanitah.com/v1/*` | spark-gateway APIs | Yes |
| Portal capacity badge | Admin Go online/offline (DynamoDB) | No (flag only) |
