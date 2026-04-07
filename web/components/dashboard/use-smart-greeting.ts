"use client";

import { useEffect, useState } from "react";

import { useSessionUserDisplay } from "@/components/app-session-gate";
import { useAppWorkspace } from "@/components/app-workspace";

function resolveBrowserTimeZone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

function resolveGreetingLabel(timeZone: string): string {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      hourCycle: "h23",
      timeZone,
    }).formatToParts(new Date());
    const hour = Number(parts.find((part) => part.type === "hour")?.value ?? 0);

    if (hour < 12) {
      return "Good morning";
    }
    if (hour < 18) {
      return "Good afternoon";
    }
    return "Good evening";
  } catch {
    const hour = new Date().getHours();
    if (hour < 12) {
      return "Good morning";
    }
    if (hour < 18) {
      return "Good afternoon";
    }
    return "Good evening";
  }
}

export function useSmartGreeting() {
  const { firstName } = useSessionUserDisplay();
  const workspace = useAppWorkspace();
  const [browserTimeZone] = useState<string | null>(() => resolveBrowserTimeZone());
  const [salutation, setSalutation] = useState<string>(() =>
    resolveGreetingLabel(browserTimeZone ?? "America/Los_Angeles"),
  );
  const businessTimeZone = workspace?.locations?.[0]?.timezone ?? null;

  const activeTimeZone =
    browserTimeZone ?? businessTimeZone ?? "America/Los_Angeles";

  useEffect(() => {
    const updateGreeting = () => {
      setSalutation(resolveGreetingLabel(activeTimeZone));
    };

    updateGreeting();
    const intervalId = window.setInterval(updateGreeting, 60_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [activeTimeZone]);

  return {
    greeting: `${salutation}, ${firstName}`,
    salutation,
    firstName,
    timeZone: activeTimeZone,
  };
}
