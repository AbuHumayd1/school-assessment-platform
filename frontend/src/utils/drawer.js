export function dismissDrawerBackdrop(event) {
  if (event.target !== event.currentTarget) return
  const rect = event.currentTarget.getBoundingClientRect()
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.currentTarget.close()
}
export function dismissDrawerCancel(event) {
  event.preventDefault()
  event.currentTarget.close()
}
export function lockDrawerScroll(body) {
  const previous = body.style.overflow
  body.style.overflow = 'hidden'
  return () => { body.style.overflow = previous }
}
