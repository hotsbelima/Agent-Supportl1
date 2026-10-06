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
          <p className="hero-index">01 / Автономный L1-агент по инцидентам</p>
          <h1>
            Инцидент расследуется по сохранённым фактам,
            <span> без показа скрытых рассуждений модели.</span>
          </h1>
          <p>
            Событийная демонстрация расследования: состояние продукта и наблюдений
            сохраняются, агент работает через native Google ADK, а побочные
            действия требуют решения человека.
          </p>
        </div>

        <div className="architecture-strip" aria-label="Краткая архитектура">
          <span>Next.js UI</span>
          <i aria-hidden="true">→</i>
          <span>FastAPI Product API</span>
          <i aria-hidden="true">→</i>
          <span>PostgreSQL</span>
          <b>Сохранённый источник истины</b>
        </div>
      </section>

      <StartScenario />

      <section className="home-principles" aria-label="Гарантии продукта">
        <article>
          <span>01</span>
          <strong>Сначала наблюдений</strong>
          <p>Наблюдаемые факты отделены от неподтверждённых предположений.</p>
        </article>
        <article>
          <span>02</span>
          <strong>Решение человека</strong>
          <p>Побочный эффект запрещён до явного одобрения.</p>
        </article>
        <article>
          <span>03</span>
          <strong>Восстановление из состояние продукта</strong>
          <p>Обновление и переподключение перечитывают сохранённую истину, а не локальную догадку UI.</p>
        </article>
      </section>
    </main>
  );
}
