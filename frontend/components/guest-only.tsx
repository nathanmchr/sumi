"use client";

import { ReactNode, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { session } from "@/lib/api";

export function GuestOnly({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { data } = useSWR("session", session, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
    onSuccess: (currentSession) => {
      if (currentSession) router.replace("/dashboard");
    },
  });
  // A sign-in mutation chooses its own destination (onboarding for registration).
  const initialSession = useRef(data);

  useEffect(() => {
    if (initialSession.current) {
      router.replace("/dashboard");
    }
  }, [router]);

  return <main className="auth-shell">{children}</main>;
}
