import { StartScenario } from "@/components/start-scenario";

export default function HomePage() {
  return (
    <main className="home-shell">
      <section className="home-hero">
        <div className="brand-lockup hero-brand">
          <span className="brand-mark" aria-hidden="true">8O</span>
          <div>
            <p className="eyebrow">Operational AI portfolio demo</p>
            <span className="brand-name">8 Щупалец · IT Operations</span>
          </div>
        </div>

        <div className="hero-copy">
          <p className="hero-index">01 / Autonomous L1 Incident Agent</p>
          <h1>
            Persistent incident handling,
            <span> visible without exposing model reasoning.</span>
          </h1>
          <p>
            A production-shaped demo of state, evidence, human approval and
            audit events. Phase 5 adds the operational surface; live six-tool
            agent investigation remains deliberately reserved for Phase 6.
          </p>
        </div>

        <div className="architecture-strip" aria-label="Architecture summary">
          <span>Next.js UI</span>
          <i aria-hidden="true">→</i>
          <span>FastAPI</span>
          <i aria-hidden="true">→</i>
          <span>PostgreSQL</span>
          <b>Persisted source of truth</b>
        </div>
      </section>

      <StartScenario />

      <section className="home-principles" aria-label="Product guarantees">
        <article>
          <span>01</span>
          <strong>Evidence first</strong>
          <p>Operational observations stay separate from unsupported claims.</p>
        </article>
        <article>
          <span>02</span>
          <strong>Human boundary</strong>
          <p>Field-service execution cannot happen before Approve.</p>
        </article>
        <article>
          <span>03</span>
          <strong>Persistent audit</strong>
          <p>Run state and timeline survive process restarts and reloads.</p>
        </article>
      </section>
    </main>
  );
}
