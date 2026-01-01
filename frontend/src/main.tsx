
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'

import { ClerkProvider } from '@clerk/clerk-react'

import posthog from 'posthog-js'
import { PostHogProvider } from 'posthog-js/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient()

// Import publishable key (Runtime first, then Build-time)
const PUBLISHABLE_KEY = window.__RUNTIME_CONFIG__?.VITE_CLERK_PUBLISHABLE_KEY || import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

// Initialize PostHog
// We use a safe check for the key, defaulting to empty string if missing to avoid crash, 
// though PostHog might warn.
const POSTHOG_KEY = window.__RUNTIME_CONFIG__?.VITE_POSTHOG_KEY || import.meta.env.VITE_POSTHOG_KEY
const POSTHOG_HOST = window.__RUNTIME_CONFIG__?.VITE_POSTHOG_HOST || import.meta.env.VITE_POSTHOG_HOST || 'https://us.i.posthog.com'

if (POSTHOG_KEY) {
    posthog.init(POSTHOG_KEY, {
        api_host: POSTHOG_HOST,
        opt_out_capturing_by_default: true, // Strict Privacy: Defauts to OFF
        person_profiles: 'identified_only',
        session_recording: {
            maskAllInputs: false,
            maskInputOptions: {
                password: true
            }
        }
    })
}

if (!PUBLISHABLE_KEY) {
    console.warn("Missing Publishable Key")
}

ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
        <ClerkProvider publishableKey={PUBLISHABLE_KEY}>
            <PostHogProvider client={posthog}>
                <QueryClientProvider client={queryClient}>
                    <App />
                </QueryClientProvider>
            </PostHogProvider>
        </ClerkProvider>
    </React.StrictMode>,
)
