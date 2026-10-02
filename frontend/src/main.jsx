import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import { LanguageModeProvider } from './context/LanguageModeContext.jsx'
import './styles/global.css'
import './styles/components.css'
import './styles/layouts.css'
import './styles/student.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider><LanguageModeProvider><App /></LanguageModeProvider></AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
