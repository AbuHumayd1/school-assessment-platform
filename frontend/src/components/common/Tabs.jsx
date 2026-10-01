export default function Tabs({ items, value, onChange, label = 'Sections' }) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {items.map(item => <button key={item.value} id={`tab-${item.value}`} type="button" role="tab" aria-selected={value === item.value} className="tabs__tab" onClick={() => onChange?.(item.value)}>{item.label}</button>)}
    </div>
  )
}
