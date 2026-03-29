type StatCardProps = {
  label: string;
  value: string | number;
  hint?: string;
};

export function StatCard({ label, value, hint }: StatCardProps) {
  return (
    <div className="metric">
      <div className="muted">{label}</div>
      <strong>{value}</strong>
      {hint ? <div className="muted" style={{ fontSize: "0.78rem", marginTop: 2 }}>{hint}</div> : null}
    </div>
  );
}
