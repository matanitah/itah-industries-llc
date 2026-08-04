import styles from "./marketing.module.css";

const projects = [
  {
    title: "Emergant",
    image: "/img/ants_recording.gif",
    href: "https://github.com/PufferAI/PufferLib",
    body: "High-performance reinforcement learning with PyTorch and CUDA that simulates ant colony behaviors through emergent AI. Contributed to PufferLib.",
  },
  {
    title: "GraphGuru",
    image: "/img/graph.jpeg",
    href: "https://github.com/matanitah/GraphGuru",
    body: "Open-source Python library for knowledge graph construction and manipulation — semantic search, entity relationships, and knowledge representation.",
  },
  {
    title: "Evolvium",
    image: "/img/evolvium.png",
    href: "https://github.com/matanitah/evolvium",
    body: "Evolution simulator modeling natural selection, genetic variation, and population dynamics — emergent patterns from simple rules.",
  },
];

export default function MarketingHome() {
  return (
    <div className={styles.page}>
      <aside className={styles.sidebar}>
        <div className={styles.circuit} aria-hidden />
        <p className={styles.brand}>Matan Itah</p>
        <nav className={styles.sideNav}>
          <a href="https://www.linkedin.com/in/matan-itah/" target="_blank" rel="noreferrer">
            LinkedIn
          </a>
          <a href="https://github.com/matanitah/" target="_blank" rel="noreferrer">
            GitHub
          </a>
        </nav>
      </aside>

      <main className={styles.main}>
        <section className={styles.hero} id="about">
          <p className={styles.quote}>
            &ldquo;What keeps me going is goals.&rdquo;
            <span> — Muhammad Ali</span>
          </p>
          <div className={styles.aboutGrid}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/img/me.png" alt="Matan Itah" className={styles.portrait} />
            <div>
              <h1>Matan Itah</h1>
              <p className={styles.lead}>
                I&apos;m a passionate AI/ML engineer and data scientist with a degree in mathematics
                and computer science from UC San Diego. With expertise in both traditional machine
                learning and large language models, I specialize in developing and deploying
                scalable AI solutions that drive real-world impact. My background in mathematics
                enables me to approach complex problems with analytical rigor, while my experience
                in software engineering allows me to build robust, production-ready systems. I
                thrive when I&apos;m applying interesting tech to real world problems, and in
                environments where I am given the freedom to innovate. In my free time, I practice
                mixed martial arts and teach yoga, and love cooking and playing guitar.
              </p>
              <ul className={styles.meta}>
                <li>
                  <strong>City:</strong> New York City, USA
                </li>
                {/* Split contact strings so Cloudflare email/phone obfuscation cannot rewrite SSR HTML. */}
                <li suppressHydrationWarning>
                  <strong>Email:</strong> {["itah.matan", "@", "gmail.com"].join("")}
                </li>
                <li suppressHydrationWarning>
                  <strong>Phone:</strong> {["(+1) 203", "-", "445", "-", "3445"].join("")}
                </li>
              </ul>
              <a className={styles.resume} href="/matan_resume.pdf" target="_blank" rel="noreferrer">
                Open resume
              </a>
            </div>
          </div>
        </section>

        <section className={styles.portfolio} id="portfolio">
          <p className={styles.sectionLabel}>
            Showcasing the AI/ML research and software engineering work I do in my free time…
          </p>
          <div className={styles.grid}>
            {projects.map((p) => (
              <article key={p.title} className={styles.card}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={p.image} alt={p.title} />
                <h3>{p.title}</h3>
                <p>{p.body}</p>
                <a href={p.href} target="_blank" rel="noreferrer">
                  View on GitHub
                </a>
              </article>
            ))}
          </div>
        </section>

        <footer className={styles.footer}>
          <span>Itah Industries LLC</span>
        </footer>
      </main>
    </div>
  );
}
