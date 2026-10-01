import Button from './Button.jsx'

export default function Pagination({ page = 1, totalPages = 1, onPageChange }) {
  return (
    <nav className="pagination" aria-label="Pagination">
      <Button variant="outline" size="small" disabled={page <= 1} onClick={() => onPageChange?.(page - 1)}>Previous</Button>
      <span className="pagination__status" aria-live="polite">Page {page} of {totalPages}</span>
      <Button variant="outline" size="small" disabled={page >= totalPages} onClick={() => onPageChange?.(page + 1)}>Next</Button>
    </nav>
  )
}
