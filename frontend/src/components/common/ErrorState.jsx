export default function ErrorState({ title = 'Something went wrong', description = 'Please try again.' }) {
  return <div className="error-state" role="alert"><strong>{title}</strong><p>{description}</p></div>
}
