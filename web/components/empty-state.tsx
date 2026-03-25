type EmptyStateProps = {
  title: string;
  body: string;
};

export function EmptyState({ title, body }: EmptyStateProps) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      <div>{body}</div>
    </div>
  );
}
