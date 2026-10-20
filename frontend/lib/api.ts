import type { DashboardStats, DueItem, GrammarItem, JLPTLevel, KanjiItem, Locale, QuizAnswer, QuizQuestion, QuizStart, QuizTurn, SearchResult, SessionRecommendation, User, UserSettings, VocabularyItem } from "@/lib/types";
import type { HomophonePage } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function homophones(q: string, locale: Locale, offset = 0) {
  const params = new URLSearchParams({ q, locale, offset: String(offset), limit: "20" });
  return request<HomophonePage>(`/content/homophones?${params}`, {
    signal: AbortSignal.timeout(15000),
  });
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export type AuthSession = { user: User; settings: UserSettings; jlpt_levels?: JLPTLevel[] };

export const AUTH_EXPIRED_EVENT = "mirai:auth-expired";
let knownUserId: string | null = null;
let refreshInFlight: Promise<void> | null = null;
let sessionGeneration = 0;
let authenticationChange = 0;

function send(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
}

async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new ApiError(response.status, typeof payload.detail === "string" ? payload.detail : "Request failed");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

async function withSessionLock<T>(operation: () => Promise<T>): Promise<T> {
  // Cookies are shared across tabs. Probe again under the lock so a second
  // tab uses the newly issued cookie instead of rotating the old one twice.
  if (typeof navigator !== "undefined" && navigator.locks) {
    return await navigator.locks.request("mirai:auth-session", operation);
  }
  return operation();
}

function renewSession(): Promise<void> {
  if (!refreshInFlight) {
    refreshInFlight = withSessionLock(async () => {
      const probe = await send("/auth/session", { cache: "no-store", signal: AbortSignal.timeout(8000) });
      let authenticated: AuthSession;
      if (probe.status === 401) {
        authenticated = await readResponse<AuthSession>(await send("/auth/refresh", {
          method: "POST", cache: "no-store", signal: AbortSignal.timeout(8000),
        }));
      } else {
        authenticated = await readResponse<AuthSession>(probe);
      }
      if (knownUserId && authenticated.user.id !== knownUserId) {
        throw new ApiError(401, "Session belongs to another account. Please sign in again.");
      }
      knownUserId = authenticated.user.id;
      sessionGeneration++;
    }).finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const generation = sessionGeneration;
  const identity = authenticationChange;
  let response = await send(path, init);
  const canRenew = !path.startsWith("/auth/") || path === "/auth/session";
  if (response.status === 401 && canRenew) {
    try {
      if (generation === sessionGeneration) await renewSession();
      if (identity !== authenticationChange) throw new ApiError(409, "Session changed. Please retry.");
      // Only retry an explicit authentication refusal, never a network failure
      // or a 5xx: a write may already have reached the server in those cases.
      response = await send(path, init);
      if (response.status === 401) await readResponse(response);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401 && typeof window !== "undefined") {
        window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
      }
      throw error;
    }
  }
  return readResponse<T>(response);
}

async function authRequest<T>(path: string, init?: RequestInit, timeoutMs = 15000): Promise<T> {
  try {
    return await request<T>(path, { ...init, cache: "no-store", signal: AbortSignal.timeout(timeoutMs) });
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(0, "Authentication service unavailable. Please try again.");
  }
}

export async function login(email: string, password: string) {
  const authenticated = await withSessionLock(() => authRequest<AuthSession & { access_token_expires_minutes: number }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  }));
  knownUserId = authenticated.user.id;
  sessionGeneration++;
  authenticationChange++;
  return authenticated;
}

export async function register(email: string, full_name: string, password: string) {
  const authenticated = await authRequest<AuthSession & { access_token_expires_minutes: number }>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, full_name, password }),
  });
  knownUserId = authenticated.user.id;
  sessionGeneration++;
  authenticationChange++;
  return authenticated;
}

export async function logout() {
  const result = await withSessionLock(() => authRequest<{ ok: boolean }>("/auth/logout", { method: "POST" }));
  knownUserId = null;
  sessionGeneration++;
  authenticationChange++;
  return result;
}

export async function session() {
  try {
    const authenticated = await authRequest<AuthSession>("/auth/session", undefined, 8000);
    if (knownUserId && authenticated.user.id !== knownUserId) {
      throw new ApiError(401, "Session belongs to another account. Please sign in again.");
    }
    knownUserId = authenticated.user.id;
    return authenticated;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401 && !knownUserId) return null;
    throw error;
  }
}

export async function dashboard() {
  return request<DashboardStats>("/content/dashboard");
}

export async function levels() {
  return request<JLPTLevel[]>("/content/levels");
}

export async function vocabulary(level?: string, q?: string, locale: Locale = "en") {
  const params = new URLSearchParams();
  if (level) params.set("level", level);
  if (q) params.set("q", q);
  params.set("locale", locale);
  return request<VocabularyItem[]>(`/content/vocabulary?${params.toString()}`);
}

export async function kanji(level?: string, q?: string, locale: Locale = "en") {
  const params = new URLSearchParams();
  if (level) params.set("level", level);
  if (q) params.set("q", q);
  params.set("locale", locale);
  return request<KanjiItem[]>(`/content/kanji?${params.toString()}`);
}

export async function grammar(level?: string, q?: string, locale: Locale = "en") {
  const params = new URLSearchParams();
  if (level) params.set("level", level);
  if (q) params.set("q", q);
  params.set("locale", locale);
  return request<GrammarItem[]>(`/content/grammar?${params.toString()}`);
}

export async function search(q: string, locale: Locale = "en") {
  const params = new URLSearchParams({ q, locale });
  return request<SearchResult[]>(`/content/search?${params.toString()}`);
}

export async function dueItems(locale: Locale = "en") {
  return request<DueItem[]>(`/learning/due?locale=${locale}`);
}

export async function sessionRecommendation() {
  return request<SessionRecommendation>("/learning/recommendation");
}

export async function startQuiz(payload: QuizStart) {
  return request<QuizTurn>("/learning/sessions", { method: "POST", body: JSON.stringify(payload) });
}

export async function getQuizTurn(id: string) {
  return request<QuizTurn>(`/learning/sessions/${id}`);
}

export async function nextQuizQuestion(id: string) {
  return request<QuizTurn>(`/learning/sessions/${id}/next`, { method: "POST" });
}

export async function beginQuizQuestion(id: string) {
  return request<QuizQuestion>(`/learning/questions/${id}/begin`, { method: "POST" });
}

export async function answerQuizQuestion(id: string, optionId: string) {
  return request<QuizAnswer>(`/learning/questions/${id}/answer`, {
    method: "POST", body: JSON.stringify({ option_id: optionId }),
  });
}

export async function updateSettings(payload: UserSettings) {
  return request<UserSettings>("/users/me/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function updateProfile(full_name: string) {
  return request<User>("/users/me", {
    method: "PATCH",
    body: JSON.stringify({ full_name }),
  });
}

export { API_URL };
