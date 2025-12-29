
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'

import { ClerkProvider } from '@clerk/clerk-react'

// Import publishable key (Runtime first, then Build-time)
const PUBLISHABLE_KEY = window.__RUNTIME_CONFIG__?.VITE_CLERK_PUBLISHABLE_KEY || import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

if (!PUBLISHABLE_KEY) {
    console.warn("Missing Publishable Key")
}

ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
        <ClerkProvider publishableKey={PUBLISHABLE_KEY}>
            <App />
        </ClerkProvider>
    </React.StrictMode>,
)
