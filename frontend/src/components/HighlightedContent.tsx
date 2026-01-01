import React from 'react';
import ReactMarkdown from 'react-markdown';
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
                        id={id}
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
