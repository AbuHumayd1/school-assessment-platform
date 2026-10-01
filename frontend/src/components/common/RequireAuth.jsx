import { Navigate, useLocation } from 'react-router-dom'
import LoadingState from './LoadingState.jsx'
import { useAuth } from '../../context/AuthContext.jsx'

export default function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <LoadingState label="Checking your session" />
  if (!user) return <Navigate to="/signin" replace state={{ from: location }} />
  return children
}
