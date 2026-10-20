import type { ReactNode } from "react";
import { GuestOnly } from "@/components/guest-only";

export default function AuthLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <GuestOnly>{children}</GuestOnly>;
}
