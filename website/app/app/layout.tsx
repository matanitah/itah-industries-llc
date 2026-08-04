import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE, verifySession } from "@/lib/session";
import { CapacityBadge } from "./CapacityBadge";
import { LogoutButton } from "./LogoutButton";
import styles from "./portal.module.css";

export default async function PortalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  const session = token ? await verifySession(token) : null;
  if (!session) {
    redirect("/login");
  }

  return (
    <div className={styles.shell}>
      <header className={styles.top}>
        <div className={styles.brandBlock}>
          <Link href="/app" className={styles.brand}>
            Itah Portal
          </Link>
          <span className={styles.user}>{session.sub}</span>
        </div>
        <nav className={styles.nav}>
          <Link href="/app/chat">Chat</Link>
          <Link href="/app/docs">Documents</Link>
        </nav>
        <div className={styles.actions}>
          <CapacityBadge />
          <LogoutButton />
        </div>
      </header>
      <main className={styles.main}>{children}</main>
    </div>
  );
}
