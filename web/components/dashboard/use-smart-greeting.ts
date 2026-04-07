"use client";

import { useEffect, useState } from "react";

import { useSessionUserDisplay } from "@/components/app-session-gate";
import { getWorkspace } from "@/lib/api/workspace";

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
  const [browserTimeZone] = useState<string | null>(() => resolveBrowserTimeZone());
  const [businessTimeZone, setBusinessTimeZone] = useState<string | null>(null);
  const [salutation, setSalutation] = useState<string>(() =>
    resolveGreetingLabel(browserTimeZone ?? "America/Los_Angeles"),
  );

  useEffect(() => {
    let cancelled = false;

    async function loadWorkspaceFallbackTimeZone() {
      try {
        const workspace = await getWorkspace();
        if (cancelled) {
          return;
        }
        setBusinessTimeZone(workspace?.locations?.[0]?.timezone ?? null);
      } catch {
        if (!cancelled) {
          setBusinessTimeZone(null);
        }
      }
    }

    void loadWorkspaceFallbackTimeZone();

    return () => {
      cancelled = true;
    };
  }, []);

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
