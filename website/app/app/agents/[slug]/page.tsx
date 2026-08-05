"use client";

import { use, useCallback, useEffect, useState } from "react";
import styles from "../../portal.module.css";
import { catalogEntry } from "../agentCatalog";

type AgentStatus = {
  agent_slug: string;
  running: boolean;
  uptime_seconds?: number | null;
  error?: string;
};

export default function AgentDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const meta = catalogEntry(slug);

  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/agents");
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.error || data.detail || `Request failed (${res.status})`);
        return;
      }
      const found = (data.agents || []).find((a: AgentStatus) => a.agent_slug === slug);
      setStatus(found || { agent_slug: slug, running: false, error: "Not entitled to this agent" });
    } catch {
      setError("Network error talking to the portal API");
    }
  }, [slug]);

  const loadDashboardUrl = useCallback(async () => {
    try {
      const res = await fetch(`/api/agents/${slug}/dashboard-url`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.error || data.detail || `Could not load dashboard (${res.status})`);
        return;
      }
      setFrameUrl(data.url);
    } catch {
      setError("Network error loading the dashboard");
    }
  }, [slug]);

  useEffect(() => {
    loadStatus();
    loadDashboardUrl();
    const id = setInterval(loadStatus, 15000);
    return () => clearInterval(id);
  }, [loadStatus, loadDashboardUrl]);

  async function toggle(action: "start" | "stop") {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/agents/${slug}/${action}`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.error || data.detail || data.message || `Request failed (${res.status})`);
      }
      await loadStatus();
    } catch {
      setError("Network error talking to the portal API");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.panel}>
      <header className={styles.panelHead}>
        <h1>
          {meta.icon} {meta.name}
        </h1>
        <p>{meta.description}</p>
        <p style={{ margin: "0.35rem 0 0", color: "var(--portal-muted)", fontSize: "0.85rem" }}>
          Shared instance — every customer entitled to this agent sees the same data and Start/Stop control.
        </p>
      </header>

      {error ? <p className={styles.error}>{error}</p> : null}

      <div className={styles.agentToolbar}>
        <span className={`${styles.badge} ${status?.running ? styles.on : styles.off}`}>
          {status ? (status.running ? "Running" : "Stopped") : "Checking…"}
        </span>
        <div>
          {status?.running ? (
            <button className={styles.stopBtn} disabled={busy} onClick={() => toggle("stop")}>
              {busy ? "Stopping…" : "⏹ Stop agent (stops it for everyone)"}
            </button>
          ) : (
            <button className={styles.startBtn} disabled={busy} onClick={() => toggle("start")}>
              {busy ? "Starting…" : "▶️ Start agent (starts it for everyone)"}
            </button>
          )}
        </div>
      </div>

      <div className={styles.agentFrameWrap}>
        {frameUrl ? (
          <iframe src={frameUrl} title={meta.name} allow="clipboard-write" />
        ) : (
          <p className={styles.empty}>Loading dashboard…</p>
        )}
      </div>
    </div>
  );
}
