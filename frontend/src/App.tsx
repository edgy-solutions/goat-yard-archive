
import React, { useState } from 'react';
import ScanViewer from './components/ScanViewer';
import ReactMarkdown from 'react-markdown';
import { MOCK_CITATION } from './mock_data';

// Types (should actully be in types.ts but putting here for single-file portability if needed)
interface EvidenceItem {
    chunk_id: string;
    content: string;
    verse_ref?: string;
    citation: string;
    vol: number;
    page: number;
    scan: { x: number; y: number; w: number; h: number } | { x: number; y: number; w: number; h: number }[] | null;
    score: number;
    footnotes?: string[];
    entities?: string[];
}

interface SearchResponse {
    answer: string;
    citations: string[];
    evidence: EvidenceItem[];
    verified: boolean;
}

function App() {
    const [query, setQuery] = useState("");
    const [loading, setLoading] = useState(false);
    const [response, setResponse] = useState<SearchResponse | null>(null);
    const [activeEvidence, setActiveEvidence] = useState<EvidenceItem | null>(null);

    // Default Image Rotation
    const [defaultImage] = useState(() => {
        const images = ['/gill1.png', '/gill2.png', '/gill3.png'];
        return images[Math.floor(Math.random() * images.length)];
    });

    // Default to MOCK if backend down/empty
    const [error, setError] = useState<string | null>(null);

    const handleSearch = async () => {
        if (!query) return;
        setLoading(true);
        setError(null);
        setResponse(null);
        setActiveEvidence(null);

        try {
            const res = await fetch('http://localhost:8000/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query }),
            });

            if (!res.ok) {
                const errText = await res.text();
                throw new Error(`Server Error: ${res.status} ${errText}`);
            }

            const data = await res.json();
            setResponse(data);
            if (data.evidence && data.evidence.length > 0) {
                setActiveEvidence(data.evidence[0]);
            }
        } catch (err) {
            console.error("Search failed, falling back to mock:", err);
            setError(err instanceof Error ? err.message : "Unknown error");
            // MOCK FALLBACK for demo/testing
            setTimeout(() => {
                const mockEv: EvidenceItem = {
                    chunk_id: "mock1",
                    content: MOCK_CITATION.text || "Mock content not found",
                    citation: "[Vol 1, p. 287]",
                    vol: 1,
                    page: 287,
                    scan: MOCK_CITATION.scan_json || { x: 0, y: 0, w: 0, h: 0 },
                    score: 1.0,
                    footnotes: ["Mock footnote 1"],
                    entities: ["Mock Entity"]
                };

                setResponse({
                    answer: "Backend unavailable. (Mock Answer) Gill discusses this in his Exposition of the Old and New Testaments...",
                    citations: ["[Vol 1, p. 123]"],
                    evidence: [mockEv],
                    verified: false
                });
                setActiveEvidence(mockEv);
            }, 500);
        } finally {
            setLoading(false);
        }
    };

    // Helper to get Image URL (Placeholder logic)
    // We now have images in /public/scans/vol{vol}_page{page}_image1.png
    // This handles multi-volume support (e.g. Genesis=vol1, Matthew=vol7)
    const getImageUrl = (ev: EvidenceItem | null) => {
        if (!ev) return "";
        return `/scans/vol${ev.vol}_page${ev.page}_image1.png`;
    };

    // We need Original Dims for the scan. 
    // In a real app, this should come from Metadata or config. 
    // We'll hardcode or use MOCK_CITATION dims for now as a default
    const getOriginalDims = (ev: EvidenceItem | null) => {
        if (!ev) return null;

        // Dimensions specific to each volume based on original scans
        if (ev.vol === 1) {
            return { w: 3584, h: 5400 };
        } else if (ev.vol === 7) {
            return { w: 3360, h: 5400 };
        }

        // Default / Fallback (Let logic default to naturalWidth or these dims)
        return { w: 3360, h: 5400 };
    };

    return (
        <div className="flex h-screen overflow-hidden font-serif bg-parchment text-amber-950">

            {/* Left Pane: Chat & Context */}
            <div className="w-1/2 flex flex-col border-r border-[#8D6E63] shadow-2xl z-10">

                {/* Header */}
                <div className="p-4 border-b border-[#5D4037] bg-wood text-gold shadow-md">
                    <h1 className="text-2xl font-bold tracking-wide">Dr. Voluminous</h1>
                    <p className="text-xs text-amber-200/80 italic">Grounded Theological AI</p>
                </div>

                {/* Main Content Area */}
                <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-[#FDFBF7]">

                    {/* Error Banner */}
                    {error && (
                        <div className="bg-red-50 border-l-4 border-red-800 text-red-900 p-4 rounded shadow-sm text-sm">
                            <strong>Connection Error:</strong> {error}
                            <div className="text-xs mt-1 text-red-700">Using mock data for demonstration.</div>
                        </div>
                    )}

                    {/* Chat Interaction */}
                    {loading && (
                        <div className="flex items-center space-x-3 text-amber-800 animate-pulse">
                            <div className="w-2 h-2 bg-amber-800 rounded-full animate-bounce" style={{ animationDelay: '0s' }}></div>
                            <div className="w-2 h-2 bg-amber-800 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                            <div className="w-2 h-2 bg-amber-800 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                            <span className="text-sm font-medium italic">Consulting the library...</span>
                        </div>
                    )}

                    {response && (
                        <div className="space-y-6">
                            {/* Answer Card */}
                            <div className="bg-[#FFFDF5] p-5 rounded-lg shadow-sm border border-[#D7CCC8]">
                                <div className="flex justify-end mb-2">
                                    {response.verified ? (
                                        <span className="flex items-center text-xs text-green-800 bg-green-100 px-2 py-1 rounded-full border border-green-200 font-bold uppercase tracking-wider">
                                            ✓ Verified Source
                                        </span>
                                    ) : (
                                        <span className="text-xs text-amber-800 bg-amber-100 px-2 py-1 rounded-full border border-amber-200">
                                            ⚠️ Potential Hallucination
                                        </span>
                                    )}
                                </div>
                                <div className="prose prose-sm max-w-none text-[#3E2723] leading-relaxed">
                                    {response.answer.split('\n').map((line, i) => (
                                        <p key={i} className="mb-2">{line}</p>
                                    ))}
                                </div>
                            </div>

                            {/* Citations / Sources */}
                            <div className="flex flex-wrap gap-2">
                                {response.evidence.map((ev, idx) => (
                                    <button
                                        key={idx}
                                        onClick={() => setActiveEvidence(ev)}
                                        className={`px-3 py-1 rounded text-sm transition-all duration-200 font-serif border
                                            ${activeEvidence?.chunk_id === ev.chunk_id
                                                ? 'bg-[#5D4037] text-amber-50 border-[#3E2723] shadow-md'
                                                : 'bg-white/50 text-[#5D4037] border-[#D7CCC8] hover:bg-[#D7CCC8]/30 hover:shadow-sm'
                                            }
                                        `}
                                    >
                                        {ev.citation}
                                    </button>
                                ))}
                            </div>

                            {/* Active Context Snippet */}
                            {activeEvidence && (
                                <div className="mt-6 border-t border-[#D7CCC8] pt-4">
                                    <h3 className="text-sm font-bold uppercase text-[#5D4037] mb-2 tracking-widest border-b border-[#D7CCC8] pb-1 inline-block">
                                        Evidence Source: {activeEvidence.verse_ref || "Unknown Verse"}
                                    </h3>

                                    {/* Entity Tags */}
                                    {activeEvidence.entities && activeEvidence.entities.length > 0 && (
                                        <div className="flex flex-wrap gap-2 mb-3 mt-2">
                                            {activeEvidence.entities.map((ent, idx) => (
                                                <span key={idx} className="bg-[#EFEBE9] text-[#4E342E] text-xs px-2 py-1 rounded font-semibold border border-[#D7CCC8] shadow-sm">
                                                    {ent}
                                                </span>
                                            ))}
                                        </div>
                                    )}

                                    <div className="p-4 bg-[#FFFDF5] border border-[#D7CCC8] rounded text-sm text-[#3E2723] shadow-inner font-merriweather leading-relaxed">
                                        <div className="prose prose-sm max-w-none prose-p:my-1 prose-p:text-[#3E2723]">
                                            <ReactMarkdown>{activeEvidence.content}</ReactMarkdown>
                                        </div>

                                        {/* Footnotes Display */}
                                        {activeEvidence.footnotes && activeEvidence.footnotes.length > 0 && (
                                            <div className="mt-4 pt-3 border-t border-[#EFEBE9] text-xs">
                                                <h4 className="font-bold text-[#8D6E63] uppercase mb-1">Original Footnotes</h4>
                                                <ul className="space-y-1 text-[#5D4037] list-disc list-inside">
                                                    {activeEvidence.footnotes.map((fn, idx) => (
                                                        <li key={idx} className="italic opacity-80">
                                                            <span>{fn}</span>
                                                        </li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Input Area */}
                <div className="p-4 border-t border-[#8D6E63] bg-[#EFEBE9] shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.1)]">
                    <div className="flex gap-3">
                        <input
                            className="flex-1 p-3 border border-[#BCAAA4] rounded bg-white text-[#3E2723] placeholder-[#A1887F] focus:outline-none focus:ring-2 focus:ring-[#8D6E63] focus:border-transparent font-serif shadow-inner"
                            placeholder="Ask Dr. Gill a theological question..."
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                        />
                        <button
                            onClick={handleSearch}
                            disabled={loading}
                            className="bg-wood text-gold px-8 py-2 rounded font-bold uppercase tracking-wide hover:bg-[#2D1B18] disabled:opacity-50 transition-colors shadow-md border border-[#2D1B18]"
                        >
                            Search
                        </button>
                    </div>
                </div>
            </div>

            {/* Right Pane: Scan Verification */}
            <div className="w-1/2 bg-[#3E2723] relative border-l-8 border-[#2D1B18] shadow-inner flex items-center justify-center p-8">
                {/* Background pattern or texture could go here */}
                <div className="w-full h-full relative shadow-2xl rounded overflow-hidden border border-[#5D4037]">
                    <ScanViewer
                        imageUrl={activeEvidence ? `/scans/vol${activeEvidence.vol}_page${activeEvidence.page}_image1.png` : defaultImage}
                        highlightBox={activeEvidence?.scan || null}
                        originalDims={getOriginalDims(activeEvidence)}
                    />

                    {/* Verification Overlay Label */}
                    <div className="absolute top-4 left-4 bg-[#2D1B18]/90 text-gold px-4 py-2 rounded-sm text-sm pointer-events-none shadow-lg border border-[#5D4037] font-serif">
                        {activeEvidence ? `Vol ${activeEvidence.vol}, Page ${activeEvidence.page}` : "Library Archive"}
                    </div>
                </div>
            </div>

        </div>
    );
}

export default App;
