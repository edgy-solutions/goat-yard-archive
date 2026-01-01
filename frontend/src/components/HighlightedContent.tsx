import React from 'react';
import ReactMarkdown from 'react-markdown';

interface HighlightedContentProps {
    content: string;
    sentenceData?: { sentence_id: string; text: string }[];
    citations?: string[]; // List of citations [ID_Sxx] from the answer
    activeIds?: string[]; // IDs to explicitly highlight (if empty, highlight nothing specific)
}

const HighlightedContent: React.FC<HighlightedContentProps> = ({
    content,
    sentenceData,
    activeIds = []
}) => {
    // If no sentence data, just return content as is
    if (!sentenceData || sentenceData.length === 0) {
        return <div className="leading-relaxed text-[#3E2723]"><ReactMarkdown>{content}</ReactMarkdown></div>;
    }

    return (
        <div className="leading-relaxed text-[#3E2723]">
            {sentenceData.map((sent) => {
                const id = sent.sentence_id;
                // Highlight IF it is in the activeIds list.
                // If activeIds is empty (no selection), NO highlights are shown.
                const isHighlighted = activeIds.includes(id) || activeIds.includes(`[${id}]`);

                return (
                    <span
                        key={id}
                        id={id}
                        className={`transition-colors duration-200 ease-in-out px-0.5 rounded mx-0.5
                            ${isHighlighted ? 'bg-yellow-200 text-black border border-yellow-300 font-medium' : 'hover:bg-amber-50'}
                        `}
                        title={id}
                    >
                        <ReactMarkdown components={{ p: 'span' }}>
                            {sent.text}
                        </ReactMarkdown>{' '}
                    </span>
                );
            })}
        </div>
    );
};

export default HighlightedContent;
