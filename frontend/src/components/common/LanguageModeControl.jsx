import { useLanguageMode } from '../../context/LanguageModeContext.jsx'

export default function LanguageModeControl({ className = '' }) {
  const { languageMode, setLanguageMode } = useLanguageMode()
  return <label className={`language-mode-control ${className}`.trim()}>
    <span className="language-mode-control__label">Language</span>
    <select aria-label="Interface language" value={languageMode} onChange={event => setLanguageMode(event.target.value)}>
      <option value="english">English</option>
      <option value="bilingual">English + العربية</option>
      <option value="arabic">العربية</option>
    </select>
  </label>
}
