"use client";

import { useEffect, useMemo, useState } from "react";

function secondsUntil(value: string | null | undefined): number {
  if (!value) return 0;
  const until = new Date(value).getTime();
  if (Number.isNaN(until)) return 0;
  return Math.max(0, Math.ceil((until - Date.now()) / 1000));
}

export function useOtpCooldown(initialValue: string | null = null) {
  const [resendAvailableAt, setResendAvailableAt] = useState<string | null>(initialValue);
  const [secondsLeft, setSecondsLeft] = useState<number>(() => secondsUntil(initialValue));

  useEffect(() => {
    setSecondsLeft(secondsUntil(resendAvailableAt));
    if (!resendAvailableAt) {
      return;
    }
    const timer = window.setInterval(() => {
      const next = secondsUntil(resendAvailableAt);
      setSecondsLeft(next);
      if (next <= 0) {
        window.clearInterval(timer);
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [resendAvailableAt]);

  const canResend = useMemo(() => secondsLeft <= 0, [secondsLeft]);

  return {
    canResend,
    resendAvailableAt,
    secondsLeft,
    startCooldown: setResendAvailableAt,
  };
}
