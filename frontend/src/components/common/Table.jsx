export default function Table({ columns, rows, rowKey = 'id', caption, emptyState = 'No items to show.' }) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        {caption && <caption className="visually-hidden">{caption}</caption>}
        <thead><tr>{columns.map(column => <th key={column.key} scope="col">{column.label}</th>)}</tr></thead>
        <tbody>
          {rows.length ? rows.map((row, index) => <tr key={row[rowKey] ?? index}>{columns.map(column => <td key={column.key}>{column.render ? column.render(row) : row[column.key]}</td>)}</tr>) : <tr><td colSpan={columns.length} className="data-table__empty">{emptyState}</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
