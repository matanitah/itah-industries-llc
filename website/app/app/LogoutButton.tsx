"use client";

import { useRouter } from "next/navigation";
import styles from "./portal.module.css";

export function LogoutButton() {
  const router = useRouter();
  return (
    <button
      type="button"
      className={styles.logout}
      onClick={async () => {
        await fetch("/api/auth/logout", { method: "POST" });
        router.push("/login");
        router.refresh();
      }}
    >
      Log out
    </button>
  );
}
