# Website + customer portal

Next.js App Router app that serves:

1. **Marketing site** (`/`) — local preview of the portfolio; live `matanitah.com` is always-on GitHub Pages (`personal-website-repo`), not the Mac tunnel
2. **Customer login** (`/login`) — username/password against DynamoDB `itah-portal-users`
3. **Portal** (`/app/chat`, `/app/docs`) — authenticated chat + Docling UI; BFF proxies to API Gateway with a portal shared secret

## Local run (no deploy)

```bash
cd website
cp .env.example .env.local
# fill PORTAL_SESSION_SECRET, PORTAL_EDGE_TOKEN, ITAH_API_BASE_URL
npm install
npm run dev
# http://localhost:3000
```

Create portal users from Spark admin (`http://127.0.0.1:8080/admin/` → Portal login) after the `itah-portal-users` table exists (requires a future `terraform apply` for that table + authorizer update).

## Env

| Variable | Purpose |
|----------|---------|
| `PORTAL_SESSION_SECRET` | Signs httpOnly session JWT |
| `PORTAL_EDGE_TOKEN` | Must match Terraform `portal_shared_token` / authorizer `PORTAL_SHARED_TOKEN` |
| `ITAH_API_BASE_URL` | API Gateway endpoint |
| `PORTAL_USERS_TABLE` | Default `itah-portal-users` |
| `AWS_REGION` | Default `us-east-1` |

## Explicit non-goals for this phase

- No GitHub Actions deploy workflows
- No DNS / Pages / `matanitah.com` cutover
- No `terraform apply` from this package
