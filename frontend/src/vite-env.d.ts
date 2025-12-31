/// <reference types="vite/client" />

interface Window {
    __RUNTIME_CONFIG__?: {
        VITE_CLERK_PUBLISHABLE_KEY?: string;
        VITE_POSTHOG_KEY?: string;
        VITE_POSTHOG_HOST?: string;
    }
}
