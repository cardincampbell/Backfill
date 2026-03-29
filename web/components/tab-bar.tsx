"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

export type Tab = {
  key: string;
  label: string;
  badge?: number;
};

type TabBarProps = {
  tabs: Tab[];
  basePath: string;
  preserveParams?: string[];
};

export function TabBar({ tabs, basePath, preserveParams = [] }: TabBarProps) {
  const searchParams = useSearchParams();
  const activeTab = searchParams.get("tab") ?? tabs[0]?.key;

  function buildHref(tabKey: string) {
    const params = new URLSearchParams();
    params.set("tab", tabKey);
    for (const key of preserveParams) {
      const value = searchParams.get(key);
      if (value) params.set(key, value);
    }
    return `${basePath}?${params.toString()}`;
  }

  return (
    <div className="tab-bar">
      {tabs.map((tab) => (
        <Link
          key={tab.key}
          href={buildHref(tab.key)}
          data-active={activeTab === tab.key ? "true" : undefined}
        >
          {tab.label}
          {tab.badge != null && tab.badge > 0 ? (
            <span className="tab-badge">{tab.badge}</span>
          ) : null}
        </Link>
      ))}
    </div>
  );
}
