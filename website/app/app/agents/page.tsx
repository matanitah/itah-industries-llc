"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import styles from "../portal.module.css";
import { catalogEntry } from "./agentCatalog";

type AgentStatus = {
  agent_slug: string;
  running: boolean;
  uptime_seconds?: number | null;
  error?: string;
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/agents");
        const data = await res.json().catch(() => ({}));
        if (cancelled) return;
        if (!res.ok) {
          setError(data.error || data.detail || `Request failed (${res.status})`);
          return;
        }
        setAgents(data.agents || []);
      } catch {
        if (!cancelled) setError("Network error talking to the portal API");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className={styles.panel}>
      <header className={styles.panelHead}>
        <h1>Agents</h1>
        <p>Long-running research agents you&apos;re entitled to. Open one to start/stop it and view its dashboard.</p>
      </header>
      {error ? <p className={styles.error}>{error}</p> : null}
      {agents === null && !error ? <p className={styles.empty}>Loading…</p> : null}
      {agents && agents.length === 0 ? (
        <p className={styles.empty}>No agents enabled on your account yet. Ask your administrator to grant access.</p>
      ) : null}
      {agents && agents.length > 0 ? (
        <div className={styles.agentGrid}>
          {agents.map((a) => {
            const meta = catalogEntry(a.agent_slug);
            return (
              <div key={a.agent_slug} className={styles.agentCard}>
                <h2>
                  {meta.icon} {meta.name}
                </h2>
                <p style={{ margin: 0, color: "var(--portal-muted)", fontSize: "0.85rem" }}>{meta.description}</p>
                <span className={`${styles.badge} ${a.running ? styles.on : styles.off}`} style={{ width: "fit-content" }}>
                  {a.running ? "Running" : "Stopped"}
                </span>
                <Link href={`/app/agents/${a.agent_slug}`}>Open dashboard →</Link>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
