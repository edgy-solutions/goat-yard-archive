import React, { useEffect } from 'react';
import { TextWithVerses } from './TextWithVerses';

interface HighlightedContentProps {
    content: string;
    sentenceData?: { sentence_id: string; text: string }[];
    lemma?: string;
    verseRef?: string; // New Verse Ref field
    citations?: string[];
    activeIds?: string[];
    footnotes?: string[];
}

const HighlightedContent: React.FC<HighlightedContentProps> = ({
    content,
    sentenceData,
    lemma,
    verseRef,
    activeIds = [],
    footnotes = []
}) => {
    // Auto-scroll to highlighted sentence when activeIds changes
    // Scrolls only within the evidence container, positions near TOP
    useEffect(() => {
        if (activeIds.length > 0) {
            const targetId = activeIds[0].replace(/[\[\]]/g, ''); // Remove brackets if present
            const element = document.getElementById(targetId);
            const container = document.getElementById('evidence-scroll-container');

            if (element && container) {
                // Use getBoundingClientRect for accurate relative positioning
                const elementRect = element.getBoundingClientRect();
                const containerRect = container.getBoundingClientRect();

                // Calculate relative position of element within container
                const relativeTop = elementRect.top - containerRect.top + container.scrollTop;

                // Scroll to position element near TOP of container (with 20px offset for breathing room)
                const targetScroll = relativeTop - 20;

                container.scrollTo({
                    top: Math.max(0, targetScroll),
                    behavior: 'smooth'
                });
            }
        }
    }, [activeIds]);

    // Render Lemma (if active)
    const lemmaNode = lemma ? (
        <span className="font-bold text-[#5D4037] mr-2">
            {verseRef && (
                <span className="mr-1">{verseRef}.</span>
            )}
            <TextWithVerses text={lemma} renderMarkdown={true} />
        </span>
    ) : null;

    // If no sentence data, just return content as is (with lemma prefixed)
    if (!sentenceData || sentenceData.length === 0) {
        return (
            <div className="leading-relaxed text-[#3E2723]">
                {lemmaNode}
                <TextWithVerses text={content} renderMarkdown={true} footnotes={footnotes} />
            </div>
        );
    }

    return (
        <div className="leading-relaxed text-[#3E2723]">
            {lemmaNode}
            {sentenceData.map((sent) => {
                const id = sent.sentence_id;
                // Highlight IF it is in the activeIds list.
                // If activeIds is empty (no selection), NO highlights are shown.
                const isHighlighted = activeIds.includes(id) || activeIds.includes(`[${id}]`);

                return (
                    <span
                        key={id}
                        id={`highlight-${id}`}
                        className={`transition-colors duration-200 ease-in-out px-0.5 rounded
                            ${isHighlighted ? 'bg-yellow-200 text-black border border-yellow-300 font-medium' : 'hover:bg-amber-50'}
                        `}
                        title={id}
                    >
                        {/* We use TextWithVerses to parse and add tooltips to Bible refs */}
                        <TextWithVerses text={sent.text} renderMarkdown={true} footnotes={footnotes} />
                    </span>
                );
            })}
        </div>
    );
};

export default HighlightedContent;
