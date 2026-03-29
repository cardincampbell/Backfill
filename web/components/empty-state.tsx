type EmptyStateProps = {
  title: string;
  body: string;
};

export function EmptyState({ title, body }: EmptyStateProps) {
  return (
    <div className="empty">
      <div className="empty-mark" aria-hidden="true" />
      <strong>{title}</strong>
      <div>{body}</div>
    </div>
  );
}
