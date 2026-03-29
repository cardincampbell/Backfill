type StatCardProps = {
  label: string;
  value: string | number;
  hint?: string;
};

export function StatCard({ label, value, hint }: StatCardProps) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <strong className="metric-value">{value}</strong>
      {hint ? <div className="metric-hint">{hint}</div> : null}
    </div>
  );
}
