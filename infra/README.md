# AWS control plane (Terraform)

Provisions the hybrid edge described in [ARCHITECTURE.md](../ARCHITECTURE.md):

- DynamoDB: customers, API keys, entitlements, spark status, **portal users**
- Lambda REQUEST authorizer (API key **or** portal BFF token + customer id; scope + Spark online)
- API Gateway HTTP API proxying to the Cloudflare Tunnel origin
- IAM policy for the Spark admin agent (includes portal-users table)

## Prerequisites

- Terraform >= 1.5
- AWS credentials with rights to create API Gateway, Lambda, DynamoDB, IAM
- A Cloudflare Tunnel hostname pointing at `http://127.0.0.1:8080` on the Spark

## Apply (when you choose — not part of the website integration phase)

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# edit spark_origin_base_url, edge_shared_token, portal_shared_token
terraform init
terraform plan
terraform apply
```

Copy outputs into `spark/.env` and `website/.env.local` (`website_env_hints`, `portal_users_table`).

Set the same `portal_shared_token` in Terraform and `PORTAL_EDGE_TOKEN` on the website BFF.

## Notes

- Authorizer Lambda packages `handler.py` only; `boto3` is provided by the Lambda Python runtime.
- Set the same `edge_shared_token` in API Gateway (tfvars) and `EDGE_SHARED_TOKEN` on Spark.
- Custom domain (`api.example.com`) is intentionally out of the first scaffold.
- No GitHub Actions deploy jobs are defined here.
