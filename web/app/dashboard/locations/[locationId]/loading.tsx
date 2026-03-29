import { TabSkeleton } from "@/components/tab-skeleton";

export default function LocationLoading() {
  return (
    <main className="section">
      <div style={{ marginBottom: 28 }}>
        <div className="skeleton" style={{ width: 100, height: 22, borderRadius: 999, marginBottom: 14 }} />
        <div className="skeleton skeleton-heading" style={{ width: "30%" }} />
        <div className="skeleton skeleton-text" style={{ width: "50%" }} />
      </div>
      <TabSkeleton />
    </main>
  );
}
