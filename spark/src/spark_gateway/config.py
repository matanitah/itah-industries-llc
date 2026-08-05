from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "spark-gateway"
    host: str = "127.0.0.1"
    port: int = 8080

    # Any host running Ollama. Leave ollama_model empty to use the first local model.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""

    docling_base_url: str = "http://127.0.0.1:5001"

    # Shared secret expected from API Gateway → tunnel origin (optional in local dev).
    edge_shared_token: str = ""

    aws_region: str = "us-east-1"
    dynamodb_customers_table: str = "itah-customers"
    dynamodb_api_keys_table: str = "itah-api-keys"
    dynamodb_entitlements_table: str = "itah-entitlements"
    dynamodb_spark_status_table: str = "itah-spark-status"
    dynamodb_portal_users_table: str = "itah-portal-users"
    dynamodb_portal_invites_table: str = "itah-portal-invites"
    dynamodb_customer_agents_table: str = "itah-customer-agents"

    # Root of the agent-spark checkout on this box (agents/<slug>/dashboard.py etc).
    # Defaults to the sibling `agent-spark/` directory in this same repo checkout.
    agent_spark_root: str = ""
    # Signs short-lived tokens for the agent-dashboard iframe (see routes/agents.py).
    # Falls back to edge_shared_token if unset so a fresh checkout works without
    # yet another secret to generate, but a dedicated value is recommended.
    agent_dashboard_token_secret: str = ""
    # Fine-grained GitHub PAT (Contents: Read and write, scoped to the
    # itah-industries-wikis org only) used by agent-spark's wiki_git.py to
    # push each agent's shared wiki. Read here (not just left for a human's
    # shell to export) because spark-gateway is what actually launches the
    # crawl-loop subprocess (see services/agents.py's AgentRegistry.start),
    # and a subprocess only inherits what its *launching process's* OS
    # environment has -- not whatever this .env file populated into pydantic
    # Settings -- unless we explicitly pass it through.
    agent_spark_github_token: str = ""

    # Public portal base used in invite links (no trailing slash).
    portal_public_base_url: str = "https://spark-origin.matanitah.com"
    # Optional verified SES identity; if empty, admin shows the invite link only.
    invite_from_email: str = ""

    admin_bind_localhost_only: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
