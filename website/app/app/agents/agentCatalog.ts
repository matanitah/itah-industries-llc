/** Display metadata for known agent-spark agents. The authoritative list of
 * which agents *exist* and which a customer is *entitled to* comes from
 * spark-gateway (see agent-spark/agents/* and the customer_agents DynamoDB
 * table) -- this is purely cosmetic labeling for the portal UI. */
export type AgentCatalogEntry = {
  slug: string;
  name: string;
  description: string;
  icon: string;
};

export const AGENT_CATALOG: Record<string, AgentCatalogEntry> = {
  "cigna-mtsinai-negotiation": {
    slug: "cigna-mtsinai-negotiation",
    name: "Cigna ↔ Mt Sinai Leverage Agent",
    description:
      "Tracks Mt Sinai financials and CMS regulatory data, scoring negotiating leverage per HCPCS code / drug.",
    icon: "⚖️",
  },
  "animal-rights-watch": {
    slug: "animal-rights-watch",
    name: "Animal Rights Watch",
    description:
      "Tracks systemic animal-rights violations and animal-cruelty case law across all 50 states.",
    icon: "🐾",
  },
};

export function catalogEntry(slug: string): AgentCatalogEntry {
  return (
    AGENT_CATALOG[slug] || {
      slug,
      name: slug,
      description: "",
      icon: "🤖",
    }
  );
}
