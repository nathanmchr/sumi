"use client";

import { ChangeEvent } from "react";

type Props = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
};

export function SearchBox({ value, onChange, placeholder = "Search" }: Props) {
  return (
    <label className="search-box">
      <span className="sr-only">{placeholder}</span>
      <input className="input" value={value} placeholder={placeholder} onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)} />
    </label>
  );
}
