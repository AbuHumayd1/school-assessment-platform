import { useLayoutEffect, useRef } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import ErrorBoundary from './components/common/ErrorBoundary.jsx'
import RouteScrollRestoration from './components/common/RouteScrollRestoration.jsx'
import RequireAuth from './components/common/RequireAuth.jsx'
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
import PlaceholderPage from './pages/PlaceholderPage.jsx'
import StudentDashboardPage from './pages/student/StudentDashboardPage.jsx'
import StudentExamsPage from './pages/student/StudentExamsPage.jsx'
import StudentExamPage from './pages/student/StudentExamPage.jsx'
import StudentResultsPage from './pages/student/StudentResultsPage.jsx'
import { getRememberedAttemptPath, recordAttemptIntegrity, rememberActiveAttempt } from './services/attempts.js'

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
  ['students', 'Students'],
  ['staff', 'Teachers & Staff'],
  ['classes', 'Classes / Cohorts'],
  ['subjects', 'Subjects'],
  ['questions', 'Questions'],
  ['exams', 'Exams'],
  ['submissions', 'Submissions'],
  ['results', 'Results'],
  ['reports', 'Reports'],
  ['settings', 'Settings'],
]

export default function App() {
  return (
    <ErrorBoundary>
      <ActiveAttemptNavigationGuard />
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
        </Route>

        <Route path="app" element={<StaffLayout />}>
          <Route index element={<PlaceholderPage title="Dashboard" />} />
          {staffPages.map(([path, title]) => (
            <Route key={path} path={path} element={<PlaceholderPage title={title} />} />
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
