"use client";

import { FormEvent, useState } from "react";
import styles from "../portal.module.css";

type Msg = { role: "user" | "assistant"; content: string };

export default function ChatPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    const next = [...messages, { role: "user" as const, content: text }];
    setMessages(next);
    setInput("");
    setBusy(true);
    try {
      const res = await fetch("/api/llm/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: next }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail =
          data.detail ||
          data.error ||
          (res.status === 403 || res.status === 401
            ? "Capacity offline or access denied"
            : `Request failed (${res.status})`);
        setError(typeof detail === "string" ? detail : JSON.stringify(detail));
        return;
      }
      const content =
        data.choices?.[0]?.message?.content ||
        data.message?.content ||
        "(empty response)";
      setMessages([...next, { role: "assistant", content }]);
    } catch {
      setError("Network error talking to the portal API");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.panel}>
      <header className={styles.panelHead}>
        <h1>Chat</h1>
        <p>Messages run on your allocated model capacity when Spark is online.</p>
      </header>
      {error ? <p className={styles.error}>{error}</p> : null}
      <div className={styles.thread}>
        {messages.length === 0 ? (
          <p className={styles.empty}>Send a message to begin.</p>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? styles.userMsg : styles.assistantMsg}>
              <span>{m.role}</span>
              <p>{m.content}</p>
            </div>
          ))
        )}
      </div>
      <form className={styles.composer} onSubmit={onSubmit}>
        <textarea
          rows={3}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask something…"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          {busy ? "Thinking…" : "Send"}
        </button>
      </form>
    </div>
  );
}
