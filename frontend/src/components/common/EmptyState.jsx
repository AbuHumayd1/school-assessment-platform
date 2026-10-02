export default function EmptyState({ title, description, action, icon = '•' }) {
  return (
    <section className="empty-state" aria-labelledby="empty-state-title">
      <span className="empty-state__icon" aria-hidden="true">{icon}</span>
      <h2 id="empty-state-title">{title}</h2>
      {description && <p>{description}</p>}
      {action && <div className="empty-state__action">{action}</div>}
    </section>
  )
}
