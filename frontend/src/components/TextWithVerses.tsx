import React from 'react';
import ReactMarkdown from 'react-markdown';
import { useQuery } from '@tanstack/react-query';

// 1. The Regex for Gill's Style
// Matches: "Rom. i. 4", "Matt. 3:16", "Genesis 1"
// Logic: (Optional Num) + (Book Prefix from Whitelist) + (Optional Dot/Suffix) + (Chapter) + (Optional Verse)
// Fix: Replaced generic `[A-Z][a-z]+` with specific book list to avoid matching "Persic v", "God i"
const BOOKS = "Gen|Exod|Lev|Num|Deut|Josh|Judg|Ruth|Sam|Kgs|Chr|Ezra|Neh|Est|Job|Ps|Prov|Eccl|Cant|Isa|Jer|Lam|Ezek|Dan|Hos|Joel|Amos|Obad|Jon|Mic|Nah|Hab|Zeph|Hag|Zech|Mal|Matt|Mark|Luke|John|Acts|Rom|Cor|Gal|Eph|Phil|Col|Thess|Tim|Tit|Phm|Heb|Jas|Pet|Jude|Rev";
const GILL_REF_REGEX = new RegExp(`[1-3]?\\s?(?:${BOOKS})[a-z]*\\.?[\\s\\xa0]+[xviXVI0-9]+\\.?(?:[:.]?[\\s\\xa0]*[0-9]+)?`, 'g');

interface VerseHoverProps {
    reference: string;
    children: React.ReactNode;
}

import { createPortal } from 'react-dom';

// Portal-based Smart Tooltip to avoid all clipping
const SimpleTooltip: React.FC<{ content: string; children: React.ReactNode }> = ({ content, children }) => {
    const [isVisible, setIsVisible] = React.useState(false);
    const [coords, setCoords] = React.useState({ top: 0, left: 0 });
    const [arrowLeft, setArrowLeft] = React.useState(0);
    const [placement, setPlacement] = React.useState<'top' | 'bottom'>('top');
    const triggerRef = React.useRef<HTMLDivElement>(null);

    const handleMouseEnter = () => {
        if (triggerRef.current) {
            const rect = triggerRef.current.getBoundingClientRect();
            const TOOLTIP_WIDTH = 320; // Estimated max width
            const TOOLTIP_HEIGHT = 150; // Estimated max height (conservative)
            const GAP = 10;
            const SCREEN_PADDING = 16;

            // 1. Calculate Top/Bottom Placement
            let top = rect.top - gap_adjustment(rect.height) - GAP; // Default: Above
            let place: 'top' | 'bottom' = 'top';

            // Flip to bottom if not enough space on top
            if (rect.top < TOOLTIP_HEIGHT) {
                top = rect.bottom + GAP;
                place = 'bottom';
            }

            // 2. Calculate Left/Right (Clamping)
            let left = rect.left + (rect.width / 2) - (TOOLTIP_WIDTH / 2);

            // Clamp to screen edges
            if (left < SCREEN_PADDING) {
                left = SCREEN_PADDING;
            } else if (left + TOOLTIP_WIDTH > window.innerWidth - SCREEN_PADDING) {
                left = window.innerWidth - TOOLTIP_WIDTH - SCREEN_PADDING;
            }

            // 3. Arrow Position (Relative to tooltip box)
            // Arrow should point to center of trigger
            // arrowX_page = rect.left + rect.width/2
            // arrowX_local = arrowX_page - tooltipLeft
            const arrowL = (rect.left + rect.width / 2) - left;

            setCoords({ top, left });
            setArrowLeft(arrowL);
            setPlacement(place);
            setIsVisible(true);
        }
    };

    const gap_adjustment = (h: number) => 0; // Placeholder if needed

    return (
        <>
            <div
                ref={triggerRef}
                className="inline-block cursor-help border-b border-dotted border-gray-400"
                onMouseEnter={handleMouseEnter}
                onMouseLeave={() => setIsVisible(false)}
            >
                {children}
            </div>
            {isVisible && createPortal(
                <div
                    className="fixed z-[99999] px-3 py-2 bg-gray-900 text-white text-xs rounded shadow-2xl min-w-[200px] max-w-[320px] pointer-events-none transition-opacity duration-200"
                    style={{
                        top: coords.top,
                        left: coords.left,
                        transform: placement === 'top' ? 'translateY(-100%)' : 'translateY(0)'
                    }}
                >
                    {content}
                    {/* Arrow */}
                    <div
                        className={`absolute w-3 h-3 bg-gray-900 rotate-45 transform -translate-x-1/2 ${placement === 'top' ? '-bottom-1.5' : '-top-1.5'}`}
                        style={{ left: arrowLeft }}
                    />
                </div>,
                document.body
            )}
        </>
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

// 2. Footnote Regex: Matches `[^1]`, `[^12]`.
const FOOTNOTE_REF_REGEX = /\[\^\d+\]/g;

interface TextWithVersesProps {
    text: string;
    renderMarkdown?: boolean;
    footnotes?: string[];
}

export const TextWithVerses: React.FC<TextWithVersesProps> = ({ text, renderMarkdown = false, footnotes = [] }) => {
    // Debug Footnotes
    // console.log("TextWithVerses Render:", { textLen: text.length, footnotesCount: footnotes.length, footnotes });

    // Determine which parts are Gill verses or Footnote Refs
    // We can use a combined splitting logic or iterative split.
    // Let's do iterative: Split by Verses first, then process text chunks for Footnotes?
    // Or just one massive regex split if we combine them?
    // Combining regexes is cleaner if they don't overlap. They shouldn't.

    // Combined Regex: (GILL_REF) | (FOOTNOTE_REF)
    // IMPORTANT: Capture groups determine the split output.
    const COMBINED_REGEX = new RegExp(`(${GILL_REF_REGEX.source})|(${FOOTNOTE_REF_REGEX.source})`, 'g');

    const parts = text.split(COMBINED_REGEX).filter(part => part !== undefined && part !== '');

    return (
        <>
            {parts.map((part, index) => {
                // 1. Is it a Verse Ref?
                if (part.match(new RegExp(`^${GILL_REF_REGEX.source}$`))) {
                    return (
                        <span key={index} className="group/verse relative inline-block cursor-help font-medium decoration-dotted underline decoration-[#D7CCC8]">
                            {/* The VerseHover component handles the tooltip and styling for the text itself */}
                            <VerseHover reference={part}>{part}</VerseHover>
                        </span>
                    );
                }

                // 2. Is it a Footnote Ref? `[^N]`
                const fnMatch = part.match(/^\[\^(\d+)\]$/);
                if (fnMatch) {
                    const fnIndex = parseInt(fnMatch[1], 10);
                    // Get footnote content by matching prefix "[ID]"
                    const fnContent = footnotes.find(f => f.startsWith(`[${fnIndex}]`)) || "Footnote content not found.";

                    const scrollToFootnote = (e: React.MouseEvent) => {
                        e.stopPropagation();
                        const el = document.getElementById(`footnote-${fnIndex}`);
                        if (el) {
                            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            // Optional: Flash highlight
                            el.classList.add('bg-yellow-100');
                            setTimeout(() => el.classList.remove('bg-yellow-100'), 2000);
                        }
                    };

                    return (
                        <span key={index} className="group/verse relative inline-block cursor-pointer align-super text-[10px] text-[#8D6E63] font-bold hover:text-[#5D4037] ml-0.5" onClick={scrollToFootnote}>
                            <SimpleTooltip content={fnContent}>
                                <span className="underline decoration-dotted decoration-[#D7CCC8]">[{fnIndex}]</span>
                            </SimpleTooltip>
                        </span>
                    );
                }

                // 3. Plain Text
                if (renderMarkdown) {
                    return (
                        <span key={index} className="inline">
                            <ReactMarkdown
                                components={{
                                    p: ({ node, ...props }) => <span {...props} /> // Render spans effectively to keep inline
                                }}
                            >
                                {part}
                            </ReactMarkdown>
                        </span>
                    );
                }

                return <span key={index}>{part}</span>;
            })}
        </>
    );
};
