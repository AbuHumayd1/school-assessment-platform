import { useEffect, useId, useRef } from 'react'
import Icon from './Icon.jsx'
import { dismissDrawerBackdrop, dismissDrawerCancel, lockDrawerScroll } from '../../utils/drawer.js'

export default function Drawer({ open, onClose, title, children, side = 'left', className = '', closeLabel = 'Close menu' }) {
  const dialogRef = useRef(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  useEffect(() => {
    if (open) return lockDrawerScroll(document.body)
  }, [open])

  return (
    <dialog ref={dialogRef} className={['ui-drawer', `ui-drawer--${side}`, className].filter(Boolean).join(' ')} aria-labelledby={titleId} onClose={onClose} onClick={dismissDrawerBackdrop} onCancel={dismissDrawerCancel}>
      <div className="ui-drawer__header">
        <span id={titleId} className="ui-drawer__title">{title}</span>
        <button className="icon-button" type="button" aria-label={closeLabel} onClick={() => dialogRef.current?.close()}><Icon name="close" /></button>
      </div>
      {children}
    </dialog>
  )
}
