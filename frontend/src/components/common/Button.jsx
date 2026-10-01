import { forwardRef } from 'react'

const Button = forwardRef(function Button({ as: Element = 'button', children, variant = 'primary', size = 'medium', loading = false, disabled = false, className = '', type = 'button', ...props }, ref) {
  const classes = ['button', `button--${variant}`, `button--${size}`, className].filter(Boolean).join(' ')
  const stateProps = Element === 'button'
    ? { type, disabled: disabled || loading, 'aria-busy': loading || undefined }
    : { 'aria-disabled': disabled || loading || undefined, tabIndex: disabled || loading ? -1 : props.tabIndex }
  return (
    <Element ref={ref} className={classes} {...stateProps} {...props}>
      {loading && <span className="spinner spinner--small" aria-hidden="true" />}
      {children}
    </Element>
  )
})

export default Button
