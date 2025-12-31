import React from 'react';
import { usePostHog } from 'posthog-js/react';
import { toast } from 'sonner';

interface ResponseActionsProps {
    responseId: string;
    onReport: () => void;
}

const ResponseActions: React.FC<ResponseActionsProps> = ({ responseId, onReport }) => {
    const posthog = usePostHog();

    const handlePositive = () => {
        posthog.capture('feedback_positive', { responseId });
        toast.success("Thanks for the feedback!");
    };

    return (
        <div className="flex gap-3 text-xs text-[#8D6E63] mt-3 items-center">
            <span className="opacity-60 uppercase tracking-widest text-[10px]">Feedback:</span>
            <button
                onClick={handlePositive}
                className="hover:text-green-700 hover:bg-green-50 px-2 py-1 rounded transition-colors flex items-center gap-1 border border-transparent hover:border-green-200"
                title="This answer was helpful"
            >
                👍 Helpful
            </button>

            <button
                onClick={onReport}
                className="hover:text-red-700 hover:bg-red-50 px-2 py-1 rounded transition-colors flex items-center gap-1 border border-transparent hover:border-red-200"
                title="Report an issue with this answer"
            >
                👎 Report Issue
            </button>
        </div>
    );
};

export default ResponseActions;
