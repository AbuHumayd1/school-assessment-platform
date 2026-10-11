import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { useLanguageMode } from '../../context/LanguageModeContext.jsx'
import { staffApiFetch } from '../../services/api.js'
import Button from '../../components/common/Button.jsx'
import Icon from '../../components/common/Icon.jsx'
import { canAccessWorkspaceCapability, canPrepareWorkspace } from '../../utils/staffCapabilities.js'
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

export function WorkspaceDashboardView({ currentWorkspace, currentRole, t, languageMode, summary, assessments, results, now = new Date() }) {
  const locale = languageMode === 'arabic' ? 'ar' : 'en'
  const number = value => new Intl.NumberFormat(locale).format(value)
  const date = value => value ? new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium', timeStyle: 'short', timeZone: summary.data?.institution?.timezone || assessments.data?.timezone || results.data?.timezone || 'UTC',
  }).format(new Date(value)) : t('Not scheduled', 'لم يحدد الموعد')
  const badge = status => <span className={`wd-badge wd-badge--${status}`}>{t(...(statuses[status] || [status, status]))}</span>
  const retry = (state, message) => <div className="wd-error" role="alert"><p>{message}</p><Button variant="outline" size="small" onClick={state.retry}>{t('Try again', 'إعادة المحاولة')}</Button></div>
  const skeleton = () => <div className="wd-skeleton" role="status" aria-label={t('Loading workspace', 'جار تحميل مساحة العمل')}><span /><span /><span /></div>
  const empty = (heading, copy) => <div className="wd-empty"><span className="wd-icon"><Icon name="clipboard" /></span><h3>{heading}</h3><p>{copy}</p></div>
  const counts = summary.data?.counts
  const isNew = counts && ['active_candidates', 'questions', 'assessments', 'results'].every(key => counts[key] === 0)
  const mode = currentWorkspace.institution.workspace_mode
  const can = capability => canAccessWorkspaceCapability(currentRole, capability, mode)
  const prepare = canPrepareWorkspace(currentRole, mode)
  const actions = [
    ...(can('assessments') && prepare ? [['/app/exams/new', 'Create assessment', 'إنشاء اختبار', 'clipboard']] : []),
    ...(can('questions') && prepare ? [['/app/questions', 'Question bank', 'بنك الأسئلة', 'book']] : []),
    ...(can('candidates') ? [['/app/students', 'Add candidates', 'إضافة مترشحين', 'users']] : []),
    ...(can('reports') ? [['/app/reports', 'View reports', 'عرض التقارير', 'chart']] : []),
  ]
  const hour = now.getHours()
  const greeting = hour < 12 ? ['Good morning', 'صباح الخير'] : hour < 17 ? ['Good afternoon', 'طاب يومك'] : ['Good evening', 'مساء الخير']
  const metrics = [
    ['active_candidates', 'Candidates', 'المترشحون', 'Active candidates', 'المترشحون النشطون', 'users'],
    ['questions', 'Questions', 'الأسئلة', 'Question bank records', 'سجلات بنك الأسئلة', 'book'],
    ['assessments', 'Assessments', 'الاختبارات', 'Across all statuses', 'في جميع الحالات', 'clipboard'],
    ['results', 'Results', 'النتائج', 'Marked result records', 'سجلات النتائج المصححة', 'chart'],
  ]
  const statusCounts = Object.entries(summary.data?.assessment_status_counts || {})
  const statusTotal = statusCounts.reduce((total, [, count]) => total + count, 0)
  function assessmentList(rows, recent = false) {
    return <ul className={`wd-list${recent ? ' wd-list--recent' : ''}`}>{rows.map(row => <li key={row.id} className="wd-assessment">
      <div className="wd-row-heading"><h3><bdi>{row.title}</bdi></h3>{badge(row.status)}</div>
      <p className="wd-assessment-context"><Icon name="book" size={16} /><bdi>{row.subject}</bdi>{row.group && <><span aria-hidden="true">·</span><bdi>{row.group}</bdi></>}</p>
      {recent ? <p className="wd-recent-context">{row.start_at ? date(row.start_at) : t('Not scheduled', 'لم يحدد الموعد')}<span aria-hidden="true"> · </span>{number(row.duration_minutes)} {t('minutes', 'دقيقة')}</p> : <dl className="wd-dates"><div><dt>{t('Starts', 'البداية')}</dt><dd>{date(row.start_at)}</dd></div>
        <div><dt>{t('Ends', 'النهاية')}</dt><dd>{date(row.end_at)}</dd></div>
        <div><dt>{t('Duration', 'المدة')}</dt><dd>{number(row.duration_minutes)} {t('minutes', 'دقيقة')}</dd></div></dl>}
      {can('assessments') && <Link className="wd-text-link" to={`/app/exams/${row.id}`} aria-label={`${t('View assessment', 'عرض الاختبار')}: ${row.title}`}>{t('View assessment', 'عرض الاختبار')}<Icon name="arrow" size={16} /></Link>}
    </li>)}</ul>
  }
  return <div className="workspace-dashboard">
    <header className="wd-header"><div className="wd-welcome"><span className="wd-eyebrow">{t(...greeting)}</span>
      <h1><bdi>{currentWorkspace.institution.name}</bdi></h1><p>{t('Here’s what’s happening across your assessment workspace.', 'إليك ما يجري في مساحة عمل الاختبارات.')}</p></div>
      <div className="wd-hero-actions">
        {can('assessments') && prepare && <Button as={Link} to="/app/exams/new"><Icon name="clipboard" size={18} />{t('Create assessment', 'إنشاء اختبار')}</Button>}
        {can('candidates') && <Button as={Link} to="/app/students" variant="outline"><Icon name="users" size={18} />{t('Add candidates', 'إضافة مترشحين')}</Button>}
      </div>
    </header>
    {summary.error ? retry(summary, t('We could not load this workspace dashboard.', 'تعذر تحميل لوحة مساحة العمل.')) : <>
      <section className="wd-metrics" aria-label={t('Workspace summary', 'ملخص مساحة العمل')} aria-busy={summary.loading}>
        {metrics.map(([key, en, ar, detailEn, detailAr, icon]) => <article className={`wd-metric wd-metric--${key}`} key={key}>
          <div className="wd-metric-top"><h2>{t(en, ar)}</h2><span className="wd-icon"><Icon name={icon} /></span></div>
          {summary.loading ? <span className="wd-number-placeholder" /> : <strong>{counts?.[key] === undefined ? '—' : number(counts[key])}</strong>}
          <p>{t(detailEn, detailAr)}</p>
        </article>)}
      </section>
      {summary.loading && <p className="wd-loading-label" role="status">{t('Loading workspace summary…', 'جار تحميل ملخص مساحة العمل…')}</p>}
      {isNew && <section className="wd-journey"><span className="wd-eyebrow">{t('Ready for your first assessment', 'استعد لاختبارك الأول')}</span>
        <h2>{t('A workspace for every assessment journey', 'مساحة عمل لكل رحلة اختبار')}</h2>
        <p>{t('Begin with candidates and questions, then prepare an assessment. Results appear after attempts are marked. Additional staff and cohorts are optional.', 'ابدأ بالمترشحين والأسئلة، ثم أعد اختبارا. تظهر النتائج بعد تصحيح المحاولات. إضافة الموظفين والمجموعات اختيارية.')}</p>
        <ol>{[['Candidates', 'المترشحون'], ['Questions', 'الأسئلة'], ['Assessment', 'الاختبار'], ['Conduct', 'إجراء الاختبار'], ['Results', 'النتائج']].map(([en, ar], i) => <li key={en}><span>{number(i + 1)}</span>{t(en, ar)}</li>)}</ol>
        {can('candidates') && <Link className="wd-text-link" to="/app/students">{t('Add candidate', 'إضافة مرشح')}<Icon name="arrow" size={16} /></Link>}
      </section>}
    </>}
    <section className="wd-panel wd-upcoming"><header><span className="wd-icon"><Icon name="clock" /></span><div><span className="wd-eyebrow">{t('Your next assessments', 'اختباراتك القادمة')}</span><h2>{t('Upcoming & active assessments', 'الاختبارات القادمة والجارية')}</h2><p>{t('Scheduled assessments whose availability has not ended.', 'الاختبارات المجدولة التي لم تنته فترة إتاحتها.')}</p></div>
      {can('assessments') && <Link className="wd-text-link wd-header-link" to="/app/exams">{t('All assessments', 'جميع الاختبارات')}<Icon name="arrow" size={16} /></Link>}</header>
      {assessments.loading ? skeleton() : assessments.error ? retry(assessments, t('Assessment information is unavailable.', 'معلومات الاختبارات غير متاحة.')) : <>
        {assessments.data.upcoming_assessments.length ? assessmentList(assessments.data.upcoming_assessments) : empty(t('No scheduled assessments yet', 'لا توجد اختبارات مجدولة بعد'), t('Scheduled assessments will appear here when their availability is set.', 'ستظهر هنا الاختبارات المجدولة عند تحديد فترة إتاحتها.'))}
        <footer>{t('Up to five records. Times follow the workspace time zone.', 'حتى خمسة سجلات. الأوقات حسب المنطقة الزمنية لمساحة العمل.')}</footer>
      </>}
    </section>
    <div className="wd-panels">
      <section className="wd-panel wd-status-panel"><header><span className="wd-icon"><Icon name="layers" /></span><div><h2>{t('Assessment pipeline', 'مسار الاختبارات')}</h2><p>{t('Assessments by their current status.', 'الاختبارات حسب حالتها الحالية.')}</p></div></header>
        {summary.loading ? skeleton() : summary.error ? retry(summary, t('We could not load this workspace dashboard.', 'تعذر تحميل لوحة مساحة العمل.')) : <div className="wd-pipeline">
          <div className="wd-distribution" aria-hidden="true">{statusCounts.map(([status, count]) => <span key={status} className={`wd-segment wd-segment--${status}`} style={{ flexGrow: count, display: count ? undefined : 'none' }} />)}</div>
          <dl>{statusCounts.map(([status, count]) => <div key={status}><dt><span className={`wd-status-dot wd-segment--${status}`} />{t(...(statuses[status] || [status, status]))}</dt><dd>{number(count)}</dd></div>)}</dl>
          {statusTotal === 0 && <p>{t('Your assessment pipeline is ready for its first assessment.', 'مسار الاختبارات جاهز لاختبارك الأول.')}</p>}
        </div>}
      </section>
      <section className="wd-panel"><header><span className="wd-icon"><Icon name="chart" /></span><div><h2>{t('Recent results', 'النتائج الأخيرة')}</h2><p>{t('The five most recently marked results.', 'آخر خمس نتائج تم تصحيحها.')}</p></div>
        {can('results') && <Link className="wd-text-link wd-header-link" to="/app/results">{t('View results', 'عرض النتائج')}<Icon name="arrow" size={16} /></Link>}</header>
        {results.loading ? skeleton() : results.error ? retry(results, t('Result information is unavailable.', 'معلومات النتائج غير متاحة.')) : results.data.recent_results.length ? <ul className="wd-list wd-results">{results.data.recent_results.map(row => <li key={row.id}>
          <div className="wd-row-heading"><h3><bdi>{row.assessment_title}</bdi></h3>{badge(row.status)}</div>
          <p>{t('Candidate ID', 'معرف المترشح')}: <bdi>{row.candidate_id}</bdi></p>
          <div className="wd-result-meta"><span>{t('Score', 'الدرجة')}: <strong><bdi>{number(Number(row.marks_obtained))} / {number(Number(row.total_marks))}</bdi></strong></span><time dateTime={row.marked_at}>{date(row.marked_at)}</time></div>
        </li>)}</ul> : empty(t('No results yet', 'لا توجد نتائج بعد'), t('Results will appear here after candidate attempts are marked.', 'ستظهر النتائج هنا بعد تصحيح محاولات المترشحين.'))}
        {counts && <footer className="wd-secondary">{counts.published_results !== undefined && <span>{t('Published results', 'النتائج المنشورة')}: <strong>{number(counts.published_results)}</strong></span>}{counts.submitted_attempts !== undefined && <span>{t('Submitted attempts', 'المحاولات المسلمة')}: <strong>{number(counts.submitted_attempts)}</strong></span>}</footer>}
      </section>
    </div>
    {!assessments.loading && !assessments.error && !!assessments.data.recent_assessments.length && <section className="wd-panel wd-recent"><header><div><h2>{t('Recently created assessments', 'الاختبارات المنشأة مؤخرا')}</h2><p>{t('Your latest assessment preparation.', 'أحدث الاختبارات قيد الإعداد.')}</p></div>{can('assessments') && <Link className="wd-text-link wd-header-link" to="/app/exams">{t('View all assessments', 'عرض جميع الاختبارات')}<Icon name="arrow" size={16} /></Link>}</header>{assessmentList(assessments.data.recent_assessments.slice(0, 3), true)}</section>}
    {!!actions.length && <section className="wd-quick-actions" aria-labelledby="wd-actions-heading"><h2 id="wd-actions-heading">{t('Quick actions', 'إجراءات سريعة')}</h2><nav aria-label={t('Workspace quick actions', 'إجراءات مساحة العمل السريعة')}>{actions.map(([to, en, ar, icon]) => <Link key={to} to={to}><Icon name={icon} size={18} />{t(en, ar)}<Icon name="arrow" size={16} /></Link>)}</nav></section>}
  </div>
}

export default function WorkspaceDashboardPage() {
  const { currentWorkspace, currentRole } = useWorkspace()
  const { label: t, languageMode } = useLanguageMode()
  const workspaceId = currentWorkspace.institution.id
  const summary = useDashboardSection(workspaceId, currentRole, '')
  const assessments = useDashboardSection(workspaceId, currentRole, 'assessments')
  const results = useDashboardSection(workspaceId, currentRole, 'results')
  return <WorkspaceDashboardView {...{ currentWorkspace, currentRole, t, languageMode, summary, assessments, results }} />
}
