"use client";

import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import useSWR, { useSWRConfig } from "swr";
import { ApiError, AUTH_EXPIRED_EVENT, logout, session } from "@/lib/api";
import { SessionReconnect } from "@/components/session-reconnect";
import { useI18n } from "@/lib/i18n";

const navItems = [
  { href: "/dashboard", label: "nav.dashboard", glyph: "道" },
  { href: "/study/lessons", label: "nav.lessons", glyph: "学" },
  { href: "/study/session", label: "nav.study", glyph: "習" },
  { href: "/review", label: "nav.reviews", glyph: "復" },
  { href: "/study/vocabulary", label: "nav.vocabulary", glyph: "語" },
  { href: "/study/kanji", label: "nav.kanji", glyph: "字" },
  { href: "/study/grammar", label: "nav.grammar", glyph: "文" },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { setLocale, t } = useI18n();
  const { mutate: mutateCache } = useSWRConfig();
  const [signingOut, setSigningOut] = useState(false);
  const [logoutFailed, setLogoutFailed] = useState(false);
  const [reconnect, setReconnect] = useState(false);
  const { data, error, mutate, isValidating } = useSWR("session", session, { revalidateOnFocus: false, shouldRetryOnError: false });

  useEffect(() => {
    const expired = () => setReconnect(true);
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, expired);
  }, []);

  useEffect(() => {
    if (error instanceof ApiError && error.status === 401 && data) setReconnect(true);
  }, [error, data]);

  useEffect(() => {
    if (data === null) {
      router.replace("/login");
    }
  }, [data, router]);

  useEffect(() => {
    if (data?.settings.interface_locale) setLocale(data.settings.interface_locale);
  }, [data?.settings.interface_locale]);

  if (data === null || (error && !data)) {
    return (
      <div className="app-shell app-shell--loading">
        <main className="workspace">
          <section className="auth-card">
            <h1>{t(data === null ? "auth.required" : "auth.connectionProblem")}</h1>
            <p className="muted" role="status">{t(data === null ? "auth.inactive" : "auth.unavailable")}</p>
            {data !== null ? (
              <button className="button button--accent" type="button" disabled={isValidating} onClick={() => { void mutate().catch(() => undefined); }}>
                {t(isValidating ? "common.loading" : "auth.retry")}
              </button>
            ) : null}
          </section>
        </main>
      </div>
    );
  }

  if (data === undefined) {
    return (
      <div className="app-shell app-shell--loading">
        <main className="workspace">
          <section className="auth-card">
            <h1>{t("auth.preparing")}</h1>
            <p className="muted" role="status">{t("auth.preparingText")}</p>
          </section>
        </main>
      </div>
    );
  }

  const initials = data?.user.full_name
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase())
    .join("")
    .slice(0, 2) || "U";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <div className="brand-lockup">
            <span className="brand-mark">學</span>
            <div>
              <span className="brand-name">Mirai Path</span>
            </div>
          </div>
        </div>
        <nav className="sidebar-nav">
          {navItems.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link key={item.href} href={item.href} className="sidebar-link" aria-current={isActive ? "page" : undefined} data-active={isActive ? "true" : "false"}>
                <span className="sidebar-link__glyph" aria-hidden="true">{item.glyph}</span>
                <span>{t(item.label)}</span>
              </Link>
            );
          })}
        </nav>
        {data ? (
          <div className="user-card">
            <Link href="/settings" className="user-card__profile" aria-label={t("nav.openSettings")} title={data.user.full_name}>
              <div className="user-card__avatar">{initials}</div>
              <div className="user-card__body">
                <strong>{data.user.full_name}</strong>
                <span>{t("common.settings")}</span>
              </div>
            </Link>
            <button
              type="button"
              className="user-card__logout"
              aria-label={t("nav.logout")}
              title={t("nav.logout")}
              disabled={signingOut}
              onClick={async () => {
                setSigningOut(true);
                setLogoutFailed(false);
                try {
                  await logout();
                  await mutate(null, { revalidate: false });
                  await mutateCache((key) => key !== "session", undefined, { revalidate: false });
                  router.replace("/login");
                } catch {
                  setLogoutFailed(true);
                } finally {
                  setSigningOut(false);
                }
              }}
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none">
                <path d="M14 8.25V5.5A1.5 1.5 0 0 0 12.5 4h-7A1.5 1.5 0 0 0 4 5.5v13A1.5 1.5 0 0 0 5.5 20h7a1.5 1.5 0 0 0 1.5-1.5v-2.75" />
                <path d="M10 12h10m-3.5-3.5L20 12l-3.5 3.5" />
              </svg>
            </button>
            {logoutFailed ? <p className="user-card__error error-text" role="alert">{t("auth.logoutFailed")}</p> : null}
          </div>
        ) : null}
      </aside>
      <main className="workspace">
        <div className="workspace-frame">{children}</div>
      </main>
      {reconnect && data ? <SessionReconnect user={data.user} onDismiss={() => setReconnect(false)}
        onConnected={async (authenticated) => {
          await mutate(authenticated, { revalidate: false });
          setReconnect(false);
        }} /> : null}
    </div>
  );
}
