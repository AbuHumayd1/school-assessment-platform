import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { useLanguageMode } from '../../context/LanguageModeContext.jsx'
import { apiFetch } from '../../services/api.js'
import { candidateAccess } from '../../services/session.js'
import { onboardingDestination } from '../../services/onboarding.js'
import { signInDestination } from '../../utils/signInDestination.js'
import Button from './Button.jsx'
import LoadingState from './LoadingState.jsx'
import LanguageModeControl from './LanguageModeControl.jsx'
import { SignOutButton } from './AccountMenu.jsx'

export default function AuthenticatedAccess() {
  const { user, refreshUser } = useAuth()
  const workspace = useWorkspace()
  const { label: t, direction } = useLanguageMode()
  const location = useLocation()
  const navigate = useNavigate()
  const [candidate, setCandidate] = useState(null)
  const [retryKey, setRetryKey] = useState(0)
  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    setCandidate(null)
    candidateAccess(apiFetch, user, { signal: controller.signal }).then(available => {
      if (!cancelled) setCandidate({ userId: user.id, available })
    }).catch(error => {
      if (cancelled) return
      if (error.status === 401) refreshUser()
      else setCandidate({ userId: user.id, error: true })
    })
    return () => { cancelled = true; controller.abort() }
  }, [user.id, user.is_candidate, refreshUser, retryKey])
  const resolved = candidate?.userId === user.id
  const loading = workspace.loading || !resolved
  const error = workspace.error || candidate?.error
  const hasWorkspace = !loading && workspace.workspaces.length > 0
  const hasCandidate = !loading && candidate.available
  const destination = !loading && !error ? signInDestination(user, workspace.workspaces, location.state?.from, hasCandidate, workspace.currentRole) : null
  useEffect(() => { if (destination) navigate(destination, { replace: true }) }, [destination, navigate])
  const retry = () => { setCandidate(null); setRetryKey(value => value + 1); workspace.retry() }
  return <section className="account-access-panel" dir={direction}>
    <LanguageModeControl />
    {loading || destination ? <LoadingState label={t('Checking your account access', 'جار التحقق من صلاحيات حسابك')} /> : error ? <>
      <h1>{t('Account access could not be checked', 'تعذر التحقق من صلاحيات الحساب')}</h1>
      <p role="alert">{t('Your session is active. Check your connection and try again.', 'جلستك نشطة. تحقق من اتصالك وحاول مرة أخرى.')}</p>
      <div className="account-access-actions"><Button onClick={retry}>{t('Try again', 'إعادة المحاولة')}</Button></div>
    </> : hasWorkspace && hasCandidate ? <>
      <h1>{t('Where would you like to continue?', 'أين تود المتابعة؟')}</h1>
      <p>{t('Your account can access a workspace and the Student Portal.', 'يمكن لحسابك الوصول إلى مساحة عمل وبوابة الطلاب.')}</p>
      <div className="account-access-actions"><Button as={Link} to="/app" replace>{t('Continue to workspace', 'المتابعة إلى مساحة العمل')}</Button><Button as={Link} to="/student" replace variant="outline">{t('Continue to Student Portal', 'المتابعة إلى بوابة الطلاب')}</Button></div>
    </> : <>
      <h1>{t('No application access yet', 'لا تتوفر صلاحية دخول إلى التطبيق حاليا')}</h1>
      <p>{t('Your account is signed in, but no active workspace or candidate access is available. Contact your organizer if you expected access.', 'تم تسجيل دخولك، لكن لا تتوفر صلاحية نشطة لمساحة عمل أو بوابة الطلاب. تواصل مع الجهة المنظمة إذا كنت تتوقع صلاحية دخول.')}</p>
      <div className="account-access-actions"><Button as={Link} to={onboardingDestination}>{t('Set up workspace', 'إعداد مساحة عمل')}</Button><Button onClick={retry} variant="outline">{t('Check access again', 'التحقق من الصلاحيات مجددا')}</Button><Button as={Link} to="/" variant="outline">{t('Return to website', 'العودة إلى الموقع')}</Button></div>
    </>}
    {!loading && !destination && <SignOutButton />}
  </section>
}
