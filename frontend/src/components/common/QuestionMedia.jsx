export default function QuestionMedia({ media = [], mode = 'staff' }) {
  return <div className="question-media">{media.map(item => {
    const url = mode === 'quick' ? `/api/v1/quick-exam/media/${item.id}/` : item.url
    // API-generated same-origin paths only; never render imported external URLs or HTML.
    if (!/^\/api\/v1\/(questions|quick-exam)\/media\/[a-f0-9-]+\/(?:\?institution=\d+)?$/.test(url || '')) return null
    return <figure key={item.id}><img src={url} alt={item.alt_text || 'Question illustration'} style={{ maxWidth: '100%', height: 'auto' }} />{item.caption && <figcaption><bdi>{item.caption}</bdi></figcaption>}</figure>
  })}</div>
}
