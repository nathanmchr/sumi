"use client";

import { ReactNode } from "react";
import clsx from "clsx";

export function TextField({ label, value, onChange, type = "text", placeholder }: { label: string; value: string; onChange: (value: string) => void; type?: string; placeholder?: string }) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      <input className="input" type={type} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

export function PrimaryButton({ children, type = "button", disabled, onClick, className }: { children: ReactNode; type?: "button" | "submit"; disabled?: boolean; onClick?: () => void; className?: string }) {
  return (
    <button type={type} className={clsx("button button--accent", className)} disabled={disabled} onClick={onClick}>
      {children}
    </button>
  );
}

export function SecondaryButton({ children, type = "button", disabled, onClick, className }: { children: ReactNode; type?: "button" | "submit"; disabled?: boolean; onClick?: () => void; className?: string }) {
  return (
    <button type={type} className={clsx("button", className)} disabled={disabled} onClick={onClick}>
      {children}
    </button>
  );
}
