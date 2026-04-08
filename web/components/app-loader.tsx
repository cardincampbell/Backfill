"use client";

import { useResolvedAppAppearance, type ResolvedAppAppearance } from "@/components/app-session-gate";

type AppLoaderProps = {
  fullscreen?: boolean;
  appearance?: ResolvedAppAppearance;
};

export function AppLoader({
  fullscreen = false,
  appearance,
}: AppLoaderProps) {
  const resolvedAppearance = useResolvedAppAppearance();
  const isDark = (appearance ?? resolvedAppearance) === "dark";

  return (
    <main
      className={`flex w-full items-center justify-center ${
        fullscreen ? "min-h-screen" : "min-h-[50vh]"
      } ${isDark ? "bg-[#081A2C]" : "bg-[#F7F8FA]"}`}
      style={{ fontFamily: "'Inter', system-ui, sans-serif" }}
    >
      <div className="flex flex-col items-center justify-center gap-4">
        <div className="flex items-center gap-3">
          <div
            className={`h-2.5 w-2.5 animate-pulse rounded-full ${
              isDark ? "bg-[#635BFF]" : "bg-[#635BFF]"
            }`}
          />
          <span
            className={`text-[44px] font-semibold tracking-[-0.04em] ${
              isDark ? "text-white" : "text-[#0A2540]"
            }`}
          >
            Backfill
          </span>
        </div>
      </div>
    </main>
  );
}
