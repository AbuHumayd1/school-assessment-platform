export function formatCandidateDate(value, timeZone) {
  if (!value) return 'Not scheduled'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Not scheduled'
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium', timeStyle: 'short', ...(timeZone ? { timeZone } : {}),
    }).format(date)
  } catch {
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
  }
}
