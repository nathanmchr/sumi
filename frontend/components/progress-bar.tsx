export function ProgressBar({ value, showLabel = true, label }: { value: number; showLabel?: boolean; label?: string }) {
  const percentage = Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;
  return (
    <div className="progress">
      <div className="progress__track" role={label ? "progressbar" : undefined} aria-label={label} aria-valuenow={label ? Math.round(percentage) : undefined} aria-valuemin={label ? 0 : undefined} aria-valuemax={label ? 100 : undefined}>
        <div className="progress__fill" style={{ width: `${percentage}%` }} />
      </div>
      {showLabel ? <span className="progress__label">{Math.round(percentage)}%</span> : null}
    </div>
  );
}
