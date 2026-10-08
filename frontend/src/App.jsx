import { useLayoutEffect, useRef } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import ErrorBoundary from './components/common/ErrorBoundary.jsx'
import RouteScrollRestoration from './components/common/RouteScrollRestoration.jsx'
import RequireAuth from './components/common/RequireAuth.jsx'
import RequireWorkspace from './components/common/RequireWorkspace.jsx'
import { useWorkspace } from './context/WorkspaceContext.jsx'
import { PlatformLayout, RequirePlatform, PlatformOverview, ClientsPage, CreateClientPage, ClientDetailPage, PlatformExamsPage, ManagedOverview } from './pages/platform/PlatformPages.jsx'
import PublicLayout from './layouts/PublicLayout.jsx'
import StaffLayout from './layouts/StaffLayout.jsx'
import StudentLayout from './layouts/StudentLayout.jsx'
import LandingPage from './pages/public/LandingPage.jsx'
import {
  AboutPage,
  ContactPage,
  FeaturesPage,
  HowItWorksPage,
  PricingPage,
  SetupPage,
  SignInPage,
} from './pages/public/PublicPages.jsx'
import { QuickExamLayout, QuickEntryPage, QuickInstructionsPage, QuickAttemptPage, QuickCompletePage, QuickAttemptNavigationGuard } from './pages/public/QuickExamPages.jsx'
import PlaceholderPage from './pages/PlaceholderPage.jsx'
import WorkspaceDashboardPage from './pages/staff/WorkspaceDashboardPage.jsx'
import ExamsPage from './pages/staff/ExamsPage.jsx'
import QuestionsPage from './pages/staff/QuestionsPage.jsx'
import PlatformLibrary, { InstitutionBanks } from './pages/platform/PlatformLibrary.jsx'
import ExamDetailPage from './pages/staff/ExamDetailPage.jsx'
import ExamFormPage from './pages/staff/ExamFormPage.jsx'
import CandidatesPage from './pages/staff/CandidatesPage.jsx'
import OutcomesCentrePage from './pages/staff/OutcomesCentrePage.jsx'
import StudentDashboardPage from './pages/student/StudentDashboardPage.jsx'
import StudentExamsPage from './pages/student/StudentExamsPage.jsx'
import StudentExamPage from './pages/student/StudentExamPage.jsx'
import StudentResultsPage from './pages/student/StudentResultsPage.jsx'
import { getRememberedAttemptPath, recordAttemptIntegrity, rememberActiveAttempt } from './services/attempts.js'
import { canAccessStaffCapability, canAccessWorkspaceCapability, canPrepareWorkspace } from './utils/staffCapabilities.js'

function ActiveAttemptNavigationGuard() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const guardedPathRef = useRef(null)

  useLayoutEffect(() => {
    const activeRoute = pathname.match(/^\/student\/exam\/(\d+)\/?$/)
    if (activeRoute) {
      const activePath = `/student/exam/${activeRoute[1]}`
      const existingPath = getRememberedAttemptPath()
      if (existingPath === activePath) guardedPathRef.current = null
      if (existingPath && existingPath !== activePath) {
        const existingAttempt = existingPath.match(/^\/student\/exam\/(\d+)\/?$/)
        if (existingAttempt) {
          if (guardedPathRef.current !== existingPath) {
            guardedPathRef.current = existingPath
            recordAttemptIntegrity(existingAttempt[1], 'navigation_attempt').then(detail => {
              window.dispatchEvent(new CustomEvent('attempt-integrity-updated', { detail: { attemptId: existingAttempt[1], state: detail } }))
            }).catch(() => {})
          }
          navigate(existingPath, { replace: true })
          return
        }
      }
      rememberActiveAttempt(activePath)
      return
    }

    const protectedPath = getRememberedAttemptPath()
    const attemptMatch = protectedPath?.match(/^\/student\/exam\/(\d+)\/?$/)
    if (!attemptMatch || pathname === '/signin') return
    if (pathname === protectedPath) {
      guardedPathRef.current = null
      return
    }
    if (guardedPathRef.current !== protectedPath) {
      guardedPathRef.current = protectedPath
      recordAttemptIntegrity(attemptMatch[1], 'navigation_attempt').then(detail => {
        window.dispatchEvent(new CustomEvent('attempt-integrity-updated', { detail: { attemptId: attemptMatch[1], state: detail } }))
      }).catch(() => {})
    }
    navigate(protectedPath, { replace: true })
  }, [pathname, navigate])

  return null
}

const staffPages = [
  ['staff', 'Teachers & Staff', 'memberships'],
  ['classes', 'Classes / Cohorts', 'groups'],
  ['subjects', 'Subjects', 'subjects'],
  ['submissions', 'Submissions', 'submissions'],
  ['results', 'Results', 'results'],
  ['reports', 'Reports', 'reports'],
  ['settings', 'Settings', 'institution_settings'],
]

function StaffIndex() {
  const { currentRole, currentWorkspace } = useWorkspace()
  if (currentWorkspace?.institution.workspace_mode === 'managed_exam') return <ManagedOverview />
  if (!canAccessStaffCapability(currentRole, 'dashboard')) return <Navigate to="/app/questions" replace />
  return <WorkspaceDashboardPage />
}

function StaffPage({ title, capability }) {
  const { currentRole, currentWorkspace } = useWorkspace()
  if (!canAccessWorkspaceCapability(currentRole, capability, currentWorkspace?.institution.workspace_mode)) return <Navigate to="/app" replace />
  if (['results', 'reports', 'submissions'].includes(capability)) return <OutcomesCentrePage section={capability} />
  return <PlaceholderPage title={title} />
}

function PreparationPage({ children }) {
  const { currentRole, currentWorkspace } = useWorkspace()
  const mode = currentWorkspace?.institution.workspace_mode
  if (!canPrepareWorkspace(currentRole, mode)) return <Navigate to="/app" replace />
  return children
}

export default function App() {
  return (
    <ErrorBoundary>
      <ActiveAttemptNavigationGuard />
      <QuickAttemptNavigationGuard />
      <RouteScrollRestoration />
      <Routes>
        <Route element={<PublicLayout />}>
          <Route index element={<LandingPage />} />
          <Route path="features" element={<FeaturesPage />} />
          <Route path="how-it-works" element={<HowItWorksPage />} />
          <Route path="pricing" element={<PricingPage />} />
          <Route path="about" element={<AboutPage />} />
          <Route path="contact" element={<ContactPage />} />
          <Route path="signin" element={<SignInPage />} />
          <Route path="setup" element={<SetupPage />} />
          <Route path="take-exam" element={<QuickEntryPage />} />
        </Route>

        <Route path="take-exam" element={<QuickExamLayout />}>
          <Route path="instructions" element={<QuickInstructionsPage />} />
          <Route path="attempt/:attemptId" element={<QuickAttemptPage />} />
          <Route path="complete" element={<QuickCompletePage />} />
        </Route>

        <Route path="platform" element={<RequirePlatform><PlatformLayout /></RequirePlatform>}>
          <Route index element={<PlatformOverview />} />
          <Route path="clients" element={<ClientsPage />} />
          <Route path="clients/new" element={<CreateClientPage />} />
          <Route path="clients/:clientId" element={<ClientDetailPage />} />
          <Route path="exams" element={<PlatformExamsPage />} />
          <Route path="reports" element={<ClientsPage reports />} />
          <Route path="library" element={<PlatformLibrary />} />
          <Route path="institution-banks" element={<InstitutionBanks />} />
          <Route path="*" element={<Navigate to="/platform" replace />} />
        </Route>

        <Route path="app" element={<RequireWorkspace><StaffLayout /></RequireWorkspace>}>
          <Route index element={<StaffIndex />} />
          <Route path="exams" element={<ExamsPage />} />
          <Route path="questions" element={<PreparationPage><QuestionsPage /></PreparationPage>} />
          <Route path="questions/import/word/:sessionId" element={<PreparationPage><QuestionsPage /></PreparationPage>} />
          <Route path="exams/new" element={<PreparationPage><ExamFormPage /></PreparationPage>} />
          <Route path="exams/:assessmentId" element={<ExamDetailPage />} />
          <Route path="exams/:assessmentId/edit" element={<PreparationPage><ExamFormPage /></PreparationPage>} />
          <Route path="students" element={<CandidatesPage />} />
          {staffPages.map(([path, title, capability]) => (
            <Route key={path} path={path} element={<StaffPage title={title} capability={capability} />} />
          ))}
          <Route path="*" element={<PlaceholderPage title="Page" />} />
        </Route>

        <Route path="student" element={<RequireAuth><StudentLayout /></RequireAuth>}>
          <Route index element={<StudentDashboardPage />} />
          <Route path="exams" element={<StudentExamsPage />} />
          <Route path="exam" element={<Navigate to="/student/exams" replace />} />
          <Route path="exam/:attemptId" element={<StudentExamPage />} />
          <Route path="results" element={<StudentResultsPage />} />
          <Route path="*" element={<PlaceholderPage title="Page" />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  )
}
