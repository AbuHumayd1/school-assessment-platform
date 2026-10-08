export default function MadaarMark({ monochrome = false, className = '' }) {
  return <svg className={`madaar-mark ${className}`.trim()} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
    <path fill="currentColor" d="M5 16 21 6v58H5zM47 6l16 10v48H47z" />
    <path fill="currentColor" opacity={monochrome ? 1 : .88} d="m27 29 14-10v45H27z" />
    <circle cx="34" cy="13" r="2.7" fill={monochrome ? 'currentColor' : 'var(--gold, #C8A85B)'} />
  </svg>
}
