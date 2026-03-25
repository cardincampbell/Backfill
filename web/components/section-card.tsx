type SectionCardProps = {
  title: string;
  children: React.ReactNode;
};

export function SectionCard({ title, children }: SectionCardProps) {
  return (
    <div className="panel">
      <h3>{title}</h3>
      {children}
    </div>
  );
}
