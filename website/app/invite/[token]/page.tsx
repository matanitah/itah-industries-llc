"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import styles from "../../login/login.module.css";

type InviteMeta = {
  email: string;
  customer_id: string;
  expires_at: string;
};

export default function InviteAcceptPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;
  const router = useRouter();

  const [meta, setMeta] = useState<InviteMeta | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch(`/api/auth/invite/${encodeURIComponent(token)}`);
        const data = await res.json().catch(() => ({}));
        if (cancelled) return;
        if (!res.ok) {
          setLoadError(data.error || "Invite unavailable");
          return;
        }
        setMeta({
          email: data.email,
          customer_id: data.customer_id,
          expires_at: data.expires_at,
        });
      } catch {
        if (!cancelled) setLoadError("Network error");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`/api/auth/invite/${encodeURIComponent(token)}/accept`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, confirm }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.error || "Could not create account");
        return;
      }
      router.push("/app/chat");
      router.refresh();
    } catch {
      setError("Network error");
    } finally {
      setLoading(false);
    }
  }

  if (loadError) {
    return (
      <div className={styles.wrap}>
        <div className={styles.card}>
          <p className={styles.eyebrow}>Itah Industries</p>
          <h1>Invite unavailable</h1>
          <p className={styles.error}>{loadError}</p>
          <a href="/login" className={styles.back}>
            ← Back to login
          </a>
        </div>
      </div>
    );
  }

  if (!meta) {
    return (
      <div className={styles.wrap}>
        <div className={styles.card}>
          <p className={styles.eyebrow}>Itah Industries</p>
          <h1>Checking invite…</h1>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <form className={styles.card} onSubmit={onSubmit}>
        <p className={styles.eyebrow}>Itah Industries</p>
        <h1>Create your account</h1>
        <p className={styles.sub}>
          Invite for <strong>{meta.email}</strong>. Expires{" "}
          {new Date(meta.expires_at).toLocaleString()}.
        </p>
        {error ? <p className={styles.error}>{error}</p> : null}
        <label>
          Username
          <input
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            minLength={3}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
        </label>
        <label>
          Confirm password
          <input
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={8}
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Creating…" : "Create account"}
        </button>
        <a href="/login" className={styles.back}>
          Already have an account? Sign in
        </a>
      </form>
    </div>
  );
}
