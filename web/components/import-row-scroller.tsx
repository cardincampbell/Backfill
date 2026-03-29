"use client";

import { useEffect } from "react";

export function ImportRowScroller({ targetId }: { targetId: string }) {
  useEffect(() => {
    const el = document.getElementById(targetId);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [targetId]);

  return null;
}
