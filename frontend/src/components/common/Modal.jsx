import { useEffect, useId, useRef } from 'react'
import Icon from './Icon.jsx'

export default function Modal({ open, onClose, title, children, footer, className = '', closeLabel = 'Close dialog', dir, canClose = true }) {
  const dialogRef = useRef(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog ref={dialogRef} dir={dir} className={['ui-modal', className].filter(Boolean).join(' ')} aria-labelledby={titleId} onClose={onClose} onCancel={event => { if (!canClose) event.preventDefault() }}>
      <div className="ui-modal__header">
        <h2 id={titleId} className="ui-modal__title">{title}</h2>
        <button className="icon-button" type="button" disabled={!canClose} aria-label={closeLabel} onClick={() => dialogRef.current?.close()}><Icon name="close" /></button>
      </div>
      <div className="ui-modal__body">{children}</div>
      {footer && <div className="ui-modal__footer">{footer}</div>}
    </dialog>
  )
}
