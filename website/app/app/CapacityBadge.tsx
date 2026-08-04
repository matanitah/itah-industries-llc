"use client";

import { useEffect, useState } from "react";
import styles from "./portal.module.css";

export function CapacityBadge() {
  const [label, setLabel] = useState("Checking…");
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/health");
        const data = await res.json().catch(() => ({}));
        if (cancelled) return;
        if (res.ok && data.ok) {
          setOnline(true);
          setLabel("Capacity online");
        } else {
          setOnline(false);
          setLabel(res.status === 401 || res.status === 403 ? "Access denied" : "Capacity offline");
        }
      } catch {
        if (!cancelled) {
          setOnline(false);
          setLabel("Capacity offline");
        }
      }
    }
    load();
    const id = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <span className={`${styles.badge} ${online ? styles.on : styles.off}`}>{label}</span>
  );
}
