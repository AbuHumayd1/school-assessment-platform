export default function Card({ children, className = '', as: Element = 'section', ...props }) {
  return <Element className={['card', className].filter(Boolean).join(' ')} {...props}>{children}</Element>
}
