import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { useLanguageMode } from '../../context/LanguageModeContext.jsx'
import { staffApiFetch } from '../../services/api.js'
import Button from '../../components/common/Button.jsx'
import Icon from '../../components/common/Icon.jsx'
import './workspace-dashboard.css'

const statuses = {
  draft: ['Draft', 'مسودة'], review: ['In review', 'قيد المراجعة'],
  approved: ['Approved', 'معتمد'], scheduled: ['Scheduled', 'مجدول'],
  archived: ['Archived', 'مؤرشف'], provisional: ['Provisional', 'أولية'],
  published: ['Published', 'منشورة'], withheld: ['Withheld', 'محجوبة'],
}

function useDashboardSection(workspaceId, role, section) {
  const [state, setState] = useState(null)
  const [retryKey, setRetryKey] = useState(0)
  const key = `${workspaceId}:${role}`
  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    setState({ key, loading: true })
    staffApiFetch(`institution/dashboard/${section ? `?section=${section}` : ''}`, { signal: controller.signal })
      .then(data => {
        const returnedId = data.institution?.id ?? data.institution_id
        if (returnedId !== workspaceId) throw new Error('Workspace context changed.')
        if (!cancelled) setState({ key, data, loading: false })
      })
      .catch(error => { if (!cancelled) setState({ key, error, loading: false }) })
    return () => { cancelled = true; controller.abort() }
  }, [workspaceId, role, section, retryKey, key])
  // A selection/role change hides old values before effects run, including retries.
  const visible = state?.key === key ? state : { loading: true }
  return { ...visible, retry: () => { setState({ key, loading: true }); setRetryKey(value => value + 1) } }
}

export default function WorkspaceDashboardPage() {
  const { currentWorkspace, currentRole } = useWorkspace()
  const { label: t, languageMode } = useLanguageMode()
  const workspaceId = currentWorkspace.institution.id
  const summary = useDashboardSection(workspaceId, currentRole, '')
  const assessments = useDashboardSection(workspaceId, currentRole, 'assessments')
  const results = useDashboardSection(workspaceId, currentRole, 'results')
  const number = value => new Intl.NumberFormat(languageMode === 'arabic' ? 'ar' : 'en').format(value)
  const date = value => value ? new Intl.DateTimeFormat(languageMode === 'arabic' ? 'ar' : 'en', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: summary.data?.institution.timezone || assessments.data?.timezone || results.data?.timezone || 'UTC',
  }).format(new Date(value)) : t('Not scheduled', 'لم يحدد الموعد')
  const badge = status => <span className={`wd-badge wd-badge--${status}`}>{t(...(statuses[status] || [status, status]))}</span>
  const retry = (state, message) => <div className="wd-error" role="alert"><p>{message}</p><Button variant="outline" size="small" onClick={state.retry}>{t('Try again', 'إعادة المحاولة')}</Button></div>
  const skeleton = () => <div className="wd-skeleton" role="status" aria-label={t('Loading workspace', 'جار تحميل مساحة العمل')}><span /><span /><span /></div>
  const empty = (heading, copy) => <div className="wd-empty"><span className="wd-icon"><Icon name="clipboard" /></span><h3>{heading}</h3><p>{copy}</p></div>
  const counts = summary.data?.counts
  const isNew = counts && ['active_candidates', 'questions', 'assessments', 'results'].every(key => counts[key] === 0)
  const metrics = [
    ['active_candidates', 'Candidates', 'المترشحون', 'Active candidates', 'المترشحون النشطون', 'users'],
    ['questions', 'Questions', 'الأسئلة', 'Question bank records', 'سجلات بنك الأسئلة', 'book'],
    ['assessments', 'Assessments', 'الاختبارات', 'Across all statuses', 'في جميع الحالات', 'clipboard'],
    ['results', 'Results', 'النتائج', 'Marked result records', 'سجلات النتائج المصححة', 'chart'],
  ]
  function assessmentList(rows) {
    return <ul className="wd-list">{rows.map(row => <li key={row.id} className="wd-assessment">
      <div className="wd-row-heading"><h3><bdi>{row.title}</bdi></h3>{badge(row.status)}</div>
      <p><bdi>{row.subject}</bdi>{row.group && <> · <bdi>{row.group}</bdi></>}</p>
      <dl className="wd-dates"><div><dt>{t('Starts', 'البداية')}</dt><dd>{date(row.start_at)}</dd></div>
        <div><dt>{t('Ends', 'النهاية')}</dt><dd>{date(row.end_at)}</dd></div>
        <div><dt>{t('Duration', 'المدة')}</dt><dd>{number(row.duration_minutes)} {t('minutes', 'دقيقة')}</dd></div></dl>
    </li>)}</ul>
  }
  return <div className="workspace-dashboard">
    <header className="wd-header"><div><span className="wd-eyebrow">{t('Assessment workspace', 'مساحة عمل الاختبارات')}</span>
      <h1>{t('Workspace dashboard', 'لوحة مساحة العمل')}</h1><p>{t('Your assessments, candidates and results in one place.', 'اختباراتك ومترشحوك ونتائجك في مكان واحد.')}</p></div>
      <span className="wd-workspace-name"><Icon name="home" /><bdi>{currentWorkspace.institution.name}</bdi></span>
    </header>
    {summary.error ? retry(summary, t('We could not load this workspace dashboard.', 'تعذر تحميل لوحة مساحة العمل.')) : <>
      <section className="wd-metrics" aria-label={t('Workspace summary', 'ملخص مساحة العمل')} aria-busy={summary.loading}>
        {metrics.map(([key, en, ar, detailEn, detailAr, icon]) => <article className="wd-metric" key={key}>
          <div className="wd-metric-top"><h2>{t(en, ar)}</h2><span className="wd-icon"><Icon name={icon} /></span></div>
          {summary.loading ? <span className="wd-number-placeholder" /> : <strong>{number(counts[key])}</strong>}
          <p>{t(detailEn, detailAr)}</p>
        </article>)}
      </section>
      {summary.loading && <p className="wd-loading-label" role="status">{t('Loading workspace summary…', 'جار تحميل ملخص مساحة العمل…')}</p>}
      {isNew && <section className="wd-journey"><span className="wd-eyebrow">{t('Ready for your first assessment', 'استعد لاختبارك الأول')}</span>
        <h2>{t('A workspace for every assessment journey', 'مساحة عمل لكل رحلة اختبار')}</h2>
        <p>{t('Begin with candidates and questions, then prepare an assessment. Results appear after attempts are marked. Additional staff and cohorts are optional.', 'ابدأ بالمترشحين والأسئلة، ثم أعد اختبارا. تظهر النتائج بعد تصحيح المحاولات. إضافة الموظفين والمجموعات اختيارية.')}</p>
        <ol>{[['Candidates', 'المترشحون'], ['Questions', 'الأسئلة'], ['Assessment', 'الاختبار'], ['Conduct', 'إجراء الاختبار'], ['Results', 'النتائج']].map(([en, ar], i) => <li key={en}><span>{number(i + 1)}</span>{t(en, ar)}</li>)}</ol>
        <Button as={Link} to="/app/students">{t('Add candidate', 'إضافة مرشح')}</Button>
      </section>}
      {counts && <section className="wd-status-panel"><h2>{t('Assessment status', 'حالات الاختبارات')}</h2><dl>
        {Object.entries(summary.data.assessment_status_counts).map(([status, count]) => <div key={status}><dt>{t(...statuses[status])}</dt><dd>{number(count)}</dd></div>)}
      </dl></section>}
    </>}
    <div className="wd-panels">
      <section className="wd-panel"><header><span className="wd-icon"><Icon name="clock" /></span><div><h2>{t('Upcoming & active assessments', 'الاختبارات القادمة والجارية')}</h2><p>{t('Scheduled assessments whose availability has not ended.', 'الاختبارات المجدولة التي لم تنته فترة إتاحتها.')}</p></div></header>
        {assessments.loading ? skeleton() : assessments.error ? retry(assessments, t('Assessment information is unavailable.', 'معلومات الاختبارات غير متاحة.')) : <>
          {assessments.data.upcoming_assessments.length ? assessmentList(assessments.data.upcoming_assessments) : empty(t('No scheduled assessments yet', 'لا توجد اختبارات مجدولة بعد'), t('Scheduled assessments will appear here when their availability is set.', 'ستظهر هنا الاختبارات المجدولة عند تحديد فترة إتاحتها.'))}
          {!!assessments.data.recent_assessments.length && <><h2 className="wd-subheading">{t('Recently created assessments', 'الاختبارات المنشأة مؤخرا')}</h2>{assessmentList(assessments.data.recent_assessments)}</>}
          <footer>{t('Up to five records in each list. Times follow the workspace time zone.', 'حتى خمسة سجلات في كل قائمة. الأوقات حسب المنطقة الزمنية لمساحة العمل.')}</footer>
        </>}
      </section>
      <section className="wd-panel"><header><span className="wd-icon"><Icon name="chart" /></span><div><h2>{t('Recent results', 'النتائج الأخيرة')}</h2><p>{t('The five most recently marked results.', 'آخر خمس نتائج تم تصحيحها.')}</p></div></header>
        {results.loading ? skeleton() : results.error ? retry(results, t('Result information is unavailable.', 'معلومات النتائج غير متاحة.')) : results.data.recent_results.length ? <ul className="wd-list wd-results">{results.data.recent_results.map(row => <li key={row.id}>
          <div className="wd-row-heading"><h3><bdi>{row.assessment_title}</bdi></h3>{badge(row.status)}</div>
          <p>{t('Candidate ID', 'معرف المترشح')}: <bdi>{row.candidate_id}</bdi></p>
          <div className="wd-result-meta"><span>{t('Score', 'الدرجة')}: <strong><bdi>{number(Number(row.marks_obtained))} / {number(Number(row.total_marks))}</bdi></strong></span><time dateTime={row.marked_at}>{date(row.marked_at)}</time></div>
        </li>)}</ul> : empty(t('No results yet', 'لا توجد نتائج بعد'), t('Results will appear here after candidate attempts are marked.', 'ستظهر النتائج هنا بعد تصحيح محاولات المترشحين.'))}
      </section>
    </div>
    {counts && <div className="wd-secondary"><span>{t('Published results', 'النتائج المنشورة')}: <strong>{number(counts.published_results)}</strong></span>
      {counts.submitted_attempts !== undefined && <span>{t('Submitted attempts', 'المحاولات المسلمة')}: <strong>{number(counts.submitted_attempts)}</strong></span>}
    </div>}
  </div>
}
