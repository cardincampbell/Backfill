export default function ShiftDetailLoading() {
  return (
    <main className="section">
      <div style={{ marginBottom: 28 }}>
        <div className="skeleton" style={{ width: 80, height: 22, borderRadius: 999, marginBottom: 14 }} />
        <div className="skeleton skeleton-heading" style={{ width: "25%" }} />
        <div className="skeleton skeleton-text" style={{ width: "45%" }} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 36 }}>
        <div className="skeleton skeleton-card" />
        <div className="skeleton skeleton-card" />
        <div className="skeleton skeleton-card" />
        <div className="skeleton skeleton-card" />
      </div>
      <div className="skeleton skeleton-table" />
    </main>
  );
}
