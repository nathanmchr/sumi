import clsx from "clsx";
import { ReactNode } from "react";

export function StatCard({ label, value, hint, tone = "neutral" }: { label: string; value: string | number; hint?: string; tone?: "neutral" | "accent" | "success" }) {
  return (
    <section className={clsx("stat-card", `stat-card--${tone}`)}>
      <p className="stat-card__label">{label}</p>
      <div className="stat-card__value">{value}</div>
      {hint ? <p className="stat-card__hint">{hint}</p> : null}
    </section>
  );
}

export function Section({ title, description, children, action, className }: { title: string; description?: string; children: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <section className={clsx("section-block", className)}>
      <header className="section-block__header">
        <div>
          <h2>{title}</h2>
          {description ? <p className="section-block__description">{description}</p> : null}
        </div>
        {action ? <div>{action}</div> : null}
      </header>
      {children}
    </section>
  );
}
