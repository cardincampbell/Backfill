"use client";

import { Loader2 } from "lucide-react";

import { useResolvedAppAppearance } from "@/components/app-session-gate";

type AppRouteStateProps = {
  title: string;
  description: string;
  loading?: boolean;
};

export function AppRouteState({
  title,
  description,
  loading = false,
}: AppRouteStateProps) {
  const isDark = useResolvedAppAppearance() === "dark";

  return (
    <div className="px-5 py-8 sm:px-8 sm:py-10 lg:px-10">
      <div
        className={`mx-auto max-w-3xl rounded-[28px] border px-6 py-12 text-center sm:px-10 ${
          isDark
            ? "border-white/[0.08] bg-[#0F2E4C]"
            : "border-[#E5E7EB] bg-white"
        }`}
      >
        <div className="flex justify-center">
          <div
            className={`flex h-12 w-12 items-center justify-center rounded-2xl ${
              isDark ? "bg-white/[0.06]" : "bg-[#F7F8FA]"
            }`}
          >
            {loading ? (
              <Loader2
                className={`h-5 w-5 animate-spin ${
                  isDark ? "text-[#C1CED8]" : "text-[#8898AA]"
                }`}
              />
            ) : (
              <div
                className={`h-2.5 w-2.5 rounded-full ${
                  isDark ? "bg-[#635BFF]" : "bg-[#635BFF]"
                }`}
              />
            )}
          </div>
        </div>
        <h1
          className={`mt-5 text-[28px] font-semibold tracking-[-0.02em] ${
            isDark ? "text-white" : "text-[#0A2540]"
          }`}
        >
          {title}
        </h1>
        <p
          className={`mx-auto mt-3 max-w-xl text-[15px] leading-7 ${
            isDark ? "text-[#C1CED8]" : "text-[#5E6D7A]"
          }`}
        >
          {description}
        </p>
      </div>
    </div>
  );
}
