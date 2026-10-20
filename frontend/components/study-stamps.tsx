import { useI18n } from "@/lib/i18n";

const WINDOW = 14;
// Small, stable tilts so the seals look hand-stamped without changing between renders.
const TILTS = [-5, 3, -2, 6, -6, 2, -3, 5, -4, 1, -7, 4, -1, 3];

function isoDay(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function StudyStamps({ studyDays }: { studyDays: string[] }) {
  const { locale, t } = useI18n();
  const studied = new Set(studyDays);
  const today = new Date();
  const days = Array.from({ length: WINDOW }, (_, index) => {
    const day = new Date(today);
    day.setDate(today.getDate() - (WINDOW - 1 - index));
    return day;
  });
  const format = new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "short" });

  return (
    <ol className="study-stamps" role="img" aria-label={t("dashboard.stamps", { count: days.filter((day) => studied.has(isoDay(day))).length })}>
      {days.map((day, index) => {
        const stamped = studied.has(isoDay(day));
        return (
          <li key={isoDay(day)} title={format.format(day)} data-stamped={stamped} data-today={index === WINDOW - 1}
            style={stamped ? { ["--tilt" as string]: `${TILTS[index]}deg` } : undefined} aria-hidden="true">
            {stamped ? "済" : null}
          </li>
        );
      })}
    </ol>
  );
}
