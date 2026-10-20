export function formatPercentage(value: number) {
  return `${Math.round(value)}%`;
}

export function formatRelativeDate(input?: string | null) {
  if (!input) return "Today";
  const date = new Date(input);
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(date);
}

