import { useState } from 'react'
import Button from '../common/Button.jsx'
import { QuestionRenderer, QuestionNavigator } from '../student/StudentComponents.jsx'

export default function ExamPreview({ paper, t, onClose }) {
  const [current, setCurrent] = useState(0)
  const [answers, setAnswers] = useState({})
  const question = paper.questions[current]
  return <section className="exam-preview"><strong className="exam-preview-label">{t('PREVIEW MODE')}</strong><h2><bdi>{paper.title}</bdi></h2><p>{t('No attempt is created. No timer is running.')}</p>{(paper.randomize_questions || paper.randomize_options) && <p>{t('Configured order is shown. Candidate question or option order may vary.')}</p>}
    {!question ? <p>{t('No questions attached')}</p> : <><QuestionRenderer question={question} value={answers[current] || []} onChange={value => setAnswers(previous => ({ ...previous, [current]: value }))} translate={t} /><QuestionNavigator questions={paper.questions} answers={answers} marked={new Set()} current={current} onSelect={setCurrent} translate={t} /></>}
    <Button variant="outline" onClick={onClose}>{t('Close preview')}</Button></section>
}
