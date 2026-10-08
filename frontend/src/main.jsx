import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import { LanguageModeProvider } from './context/LanguageModeContext.jsx'
import { WorkspaceProvider } from './context/WorkspaceContext.jsx'
import { ThemeProvider } from './context/ThemeContext.jsx'
import './styles/global.css'
import './styles/components.css'
import './styles/layouts.css'
import './styles/student.css'
import './styles/theme.css'
import './styles/public-polish.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <WorkspaceProvider>
          <LanguageModeProvider><ThemeProvider><App /></ThemeProvider></LanguageModeProvider>
        </WorkspaceProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
