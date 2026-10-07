import React from 'react'

export default function ImmediateScore({ score, t = text => text }) {
  if (!score) return null
  const { marks_obtained: obtained, total_marks: total } = score
  const decimal = value => typeof value === 'string' && /^\d+(\.\d+)?$/.test(value)
  if (!decimal(obtained) || !decimal(total) || Number(total) <= 0 || Number(obtained) > Number(total)) return null
  const display = value => value.replace(/(\.\d*?[1-9])0+$|\.0+$/, '$1')
  return <div className="exam-immediate-score"><p>{t('Your score')}</p><p><strong>{display(obtained)} / {display(total)}</strong></p></div>
}
