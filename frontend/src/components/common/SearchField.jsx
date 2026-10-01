import Icon from './Icon.jsx'

export default function SearchField({ id = 'search', label = 'Search', placeholder = 'Search', className = '', ...props }) {
  return (
    <div className={['search-field', className].filter(Boolean).join(' ')}>
      <label className="visually-hidden" htmlFor={id}>{label}</label>
      <Icon name="search" className="search-field__icon" />
      <input id={id} type="search" className="form-control search-field__input" placeholder={placeholder} {...props} />
    </div>
  )
}
