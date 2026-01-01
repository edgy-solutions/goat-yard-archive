import React from 'react';
import { useQuery } from '@tanstack/react-query';
// Simple Tooltip Implementation (Inline for now if UI lib missing)
// Or use Radix if available? Let's assume we need to build a simple one or use native title for MVP fallback
// But user requested "Tooltip" component. Let's create a minimal one here if not importing.

// 1. The Regex for Gill's Style
// Matches: "Rom. i. 4", "Matt. 3:16", "Genesis 1"
// Logic: (Optional Num) + (Book Prefix from Whitelist) + (Optional Dot/Suffix) + (Chapter) + (Optional Verse)
// Fix: Replaced generic `[A-Z][a-z]+` with specific book list to avoid matching "Persic v", "God i"
const BOOKS = "Gen|Exod|Lev|Num|Deut|Josh|Judg|Ruth|Sam|Kgs|Chr|Ezra|Neh|Est|Job|Ps|Prov|Eccl|Cant|Isa|Jer|Lam|Ezek|Dan|Hos|Joel|Amos|Obad|Jon|Mic|Nah|Hab|Zeph|Hag|Zech|Mal|Matt|Mark|Luke|John|Acts|Rom|Cor|Gal|Eph|Phil|Col|Thess|Tim|Tit|Phm|Heb|Jas|Pet|Jude|Rev";
const GILL_REF_REGEX = new RegExp(`([1-3]?\\s?(?:${BOOKS})[a-z]*\\.?[\\s\\xa0]+[xviXVI0-9]+\\.?(?::\\s?[0-9]*)?)`, 'g');

interface VerseHoverProps {
    reference: string;
    children: React.ReactNode;
}

// Minimal Tooltip Wrapper (Tailwind group-hover)
const SimpleTooltip: React.FC<{ content: string; children: React.ReactNode }> = ({ content, children }) => {
    return (
        <div className="relative inline-block group">
            {children}
            <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none w-64 z-50">
                {content}
                {/* Arrow */}
                <div className="absolute top-full left-1/2 transform -translate-x-1/2 border-4 border-transparent border-t-gray-900"></div>
            </div>
        </div>
    );
};

// 2. The Hover Component
const VerseHover: React.FC<VerseHoverProps> = ({ reference, children }) => {
    // Fetch verse text on hover (or pre-fetch)
    const { data, isLoading } = useQuery({
        queryKey: ['verse', reference],
        queryFn: async () => {
            const res = await fetch(`/api/verse/${encodeURIComponent(reference)}`);
            if (!res.ok) throw new Error("Not found");
            return res.json();
        },
        enabled: true, // Eager load for now to test, or we can make it lazy on hover? 
        // React Query caches aggressively so eager is fine for visible text.
        retry: false
    });

    const tooltipContent = isLoading ? "Loading..." : (data?.text || "Verse text not found");

    return (
        <SimpleTooltip content={tooltipContent}>
            <span
                className="text-amber-700 underline decoration-dotted cursor-help decoration-amber-400/50 hover:text-amber-900 hover:decoration-amber-600 transition-colors"
            >
                {children}
            </span>
        </SimpleTooltip>
    );
};

// 3. The Parser Component
export const TextWithVerses: React.FC<{ text: string }> = ({ text }) => {
    if (!text) return null;
    const parts = text.split(GILL_REF_REGEX);

    return (
        <span>
            {parts.map((part, i) => {
                // If this part matches the regex, wrap it
                if (part.match(GILL_REF_REGEX) && part.trim().length > 3) { // Minimal length check to avoid noise
                    return <VerseHover key={i} reference={part}>{part}</VerseHover>;
                }
                return part;
            })}
        </span>
    );
};
