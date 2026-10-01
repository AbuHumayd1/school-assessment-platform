import { Navigate, Route, Routes } from 'react-router-dom'
import ErrorBoundary from './components/common/ErrorBoundary.jsx'
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

        <Route path="student" element={<StudentLayout />}>
          <Route index element={<StudentDashboardPage />} />
          <Route path="exams" element={<StudentExamsPage />} />
          <Route path="exam" element={<StudentExamPage />} />
          <Route path="results" element={<StudentResultsPage />} />
          <Route path="*" element={<PlaceholderPage title="Page" />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  )
}
