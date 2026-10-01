import { cloneElement, isValidElement } from 'react'

export function Label({ htmlFor, children, required = false, className = '' }) {
  return <label className={['form-label', className].filter(Boolean).join(' ')} htmlFor={htmlFor}>{children}{required && <span aria-hidden="true" className="form-label__required"> *</span>}</label>
}

export function FormField({ id, label, hint, error, required = false, children, className = '' }) {
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ') || undefined
  const control = isValidElement(children)
    ? cloneElement(children, {
      id: children.props.id || id,
      'aria-describedby': children.props['aria-describedby'] || describedBy,
      'aria-invalid': error ? 'true' : children.props['aria-invalid'],
    })
    : children

  return (
    <div className={['form-field', className].filter(Boolean).join(' ')}>
      {label && <Label htmlFor={id} required={required}>{label}</Label>}
      {control}
      {hint && <p className="form-hint" id={`${id}-hint`}>{hint}</p>}
      {error && <p className="form-error" id={`${id}-error`} role="alert">{error}</p>}
    </div>
  )
}

export function Input({ className = '', ...props }) {
  return <input className={['form-control', className].filter(Boolean).join(' ')} {...props} />
}

export function Select({ className = '', children, ...props }) {
  return <select className={['form-control', 'form-select', className].filter(Boolean).join(' ')} {...props}>{children}</select>
}

export function Textarea({ className = '', ...props }) {
  return <textarea className={['form-control', 'form-textarea', className].filter(Boolean).join(' ')} {...props} />
}

export function Checkbox({ id, label, className = '', ...props }) {
  return <label className={['choice-control', className].filter(Boolean).join(' ')} htmlFor={id}><input id={id} type="checkbox" {...props} /><span>{label}</span></label>
}

export function Radio({ id, label, className = '', ...props }) {
  return <label className={['choice-control', className].filter(Boolean).join(' ')} htmlFor={id}><input id={id} type="radio" {...props} /><span>{label}</span></label>
}
