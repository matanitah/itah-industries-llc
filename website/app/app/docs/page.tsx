"use client";

import { FormEvent, useState } from "react";
import styles from "../portal.module.css";

export default function DocsPage() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/docling/convert", { method: "POST", body: form });
      const text = await res.text();
      let parsed: unknown = text;
      try {
        parsed = JSON.parse(text);
      } catch {
        /* keep raw */
      }
      if (!res.ok) {
        const detail =
          typeof parsed === "object" && parsed && "error" in parsed
            ? String((parsed as { error: string }).error)
            : text || `Request failed (${res.status})`;
        setError(
          res.status === 403 || res.status === 401
            ? "Capacity offline or access denied"
            : detail,
        );
        return;
      }
      setResult(typeof parsed === "string" ? parsed : JSON.stringify(parsed, null, 2));
    } catch {
      setError("Network error talking to the portal API");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.panel}>
      <header className={styles.panelHead}>
        <h1>Documents</h1>
        <p>Upload a file for Docling conversion when document capacity is online.</p>
      </header>
      {error ? <p className={styles.error}>{error}</p> : null}
      <form className={styles.upload} onSubmit={onSubmit}>
        <input
          type="file"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !file}>
          {busy ? "Converting…" : "Convert"}
        </button>
      </form>
      {result ? (
        <pre className={styles.result}>
          <code>{result}</code>
        </pre>
      ) : null}
    </div>
  );
}
