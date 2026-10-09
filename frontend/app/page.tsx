import { StartScenario } from "@/components/start-scenario";

export default function HomePage() {
  return (
    <main className="home-shell">
      <section className="home-hero">
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
