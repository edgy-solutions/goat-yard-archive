import { useEffect, useState } from 'react';
import { useUser } from '@clerk/clerk-react';
import { usePostHog } from 'posthog-js/react';

export default function AnalyticsManager() {
    const { user, isSignedIn, isLoaded } = useUser();
    const posthog = usePostHog();
    const [showConsentModal, setShowConsentModal] = useState(false);
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        // 1. Wait for Clerk to load
        if (!isLoaded) return;

        // 2. LOGGED IN STRATEGY (The "Partner")
        if (isSignedIn && user) {
            // Check if they actually agreed (Clerk's Native Field or our Backfill)
            // Note: casting user to any because legalAcceptedAt might not be in the strict type yet
            const nativeConsent = (user as any).legalAcceptedAt;
            // Backfill check for existing users
            const backfillConsent = (user.unsafeMetadata as any)?.legalConsentDate;

            if (nativeConsent || backfillConsent) {
                // ✅ They signed the contract -> Turn on Tracking
                if (!posthog.has_opted_in_capturing()) {
                    posthog.opt_in_capturing();

                    // Identify them now that it is safe
                    posthog.identify(user.id, {
                        email: user.primaryEmailAddress?.emailAddress,
                        role: user.publicMetadata?.role
                    });
                }
                // Ensure modal is closed if they have consented
                setShowConsentModal(false);
            } else {
                // ⚠️ Edge Case: Old user (you) who created account BEFORE you enabled the setting.
                // Option B: Show a modal forcing them to accept.
                console.warn("User logged in but has no legal acceptance date. Requesting consent.");
                // Ensure tracking is off until they consent
                if (posthog.has_opted_in_capturing()) {
                    posthog.opt_out_capturing();
                }
                setShowConsentModal(true);
            }
        }

        // 3. ANONYMOUS STRATEGY (The "Visitor")
        else if (!isSignedIn) {
            // Ensure we are NOT tracking anonymous users (as per your compromise)
            if (posthog.has_opted_in_capturing()) {
                posthog.opt_out_capturing();
                posthog.reset(); // Clear any old data
            }
        }
    }, [isLoaded, isSignedIn, user, posthog]);

    const handleAccept = async () => {
        if (!user) return;
        setSubmitting(true);
        try {
            // Update unsafeMetadata to record consent
            await user.update({
                unsafeMetadata: {
                    ...user.unsafeMetadata,
                    legalConsentDate: new Date().toISOString()
                }
            });
            // The useEffect will react to the user update and enable PostHog
            setShowConsentModal(false);
        } catch (err) {
            console.error("Failed to save consent:", err);
        } finally {
            setSubmitting(false);
        }
    };

    if (!showConsentModal) return null;

    // Force Consent Modal
    return (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-300">
            <div className="bg-[#FDFBF7] border border-[#8D6E63] rounded-lg shadow-2xl max-w-lg w-full p-6 text-center">
                <h2 className="text-xl font-bold text-[#3E2723] mb-4 uppercase tracking-wide font-serif">
                    Update to Legal Terms
                </h2>
                <p className="text-[#5D4037] mb-6 leading-relaxed">
                    We have updated our <strong>Terms of Use</strong> and <strong>Privacy Policy</strong> to better protect your data and explain our use of AI.
                    <br /><br />
                    To continue using Dr. Voluminous, you must acknowledge these updates.
                </p>

                <div className="flex justify-center gap-4 text-sm mb-8">
                    <a href="/?view=terms" target="_blank" className="text-amber-800 underline hover:text-[#3E2723]">Read Terms</a>
                    <span className="text-[#D7CCC8]">|</span>
                    <a href="/?view=privacy" target="_blank" className="text-amber-800 underline hover:text-[#3E2723]">Read Privacy Policy</a>
                </div>

                <button
                    onClick={handleAccept}
                    disabled={submitting}
                    className="w-full bg-wood text-gold py-3 rounded font-bold uppercase tracking-wider hover:bg-[#2D1B18] transition-colors disabled:opacity-50 shadow-md"
                >
                    {submitting ? "Saving..." : "I Agree & Continue"}
                </button>
            </div>
        </div>
    );
}
