import { StartScenario } from "@/components/start-scenario";

export default function HomePage() {
  return (
    <main className="home-shell">
      <section className="home-hero">
        <div className="brand-lockup hero-brand">
          <span className="brand-mark" aria-hidden="true">8O</span>
          <div>
            <p className="eyebrow">Публичное демо операционного AI</p>
            <span className="brand-name">8 Щупалец · IT-операции</span>
          </div>
        </div>

        <div className="hero-copy">
          <h1>Автономный L1 Support Agent</h1>
          <p>
            Расследует инциденты, собирает факты из рабочих систем, предлагает
            решение и передаёт потенциально опасные действия на подтверждение
            человеку.
          </p>
        </div>
      </section>

      <StartScenario />
    </main>
  );
}
