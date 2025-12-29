
import { useState } from 'react';
import ScanGallery from './components/ScanGallery';
import ReactMarkdown from 'react-markdown';
import { MOCK_CITATION } from './mock_data';
import Header from './components/Header';
import { useAuth } from '@clerk/clerk-react';

// Types (should actully be in types.ts but putting here for single-file portability if needed)
interface Rect { x: number; y: number; w: number; h: number; }

interface ScanPageHighlight {
    vol: number;
    page: number;
    boxes: Rect[];
}

interface EvidenceItem {
    chunk_id: string;
    content: string;
    verse_ref?: string;
    citation: string;
    vol: number;
    page: number;
    // scan can be legacy Rect[] or new ScanPageHighlight[]
    scan: Rect[] | ScanPageHighlight[] | null;
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
    const { getToken } = useAuth();

    // Track the query that ACTUALLY produced the results, for highlighting
    const [lastSearchedQuery, setLastSearchedQuery] = useState("");

    // Default Image Rotation
    const [defaultImage] = useState(() => {
        const images = ['/scans/gill1.png', '/scans/gill2.png', '/scans/gill3.png'];
        return images[Math.floor(Math.random() * images.length)];
    });

    // Default to MOCK if backend down/empty
    const [error, setError] = useState<string | null>(null);

    const handleSearch = async () => {
        if (!query) return;
        setLoading(true);
        setError(null);
        setResponse(null);
        setResponse(null);
        setActiveEvidence(null);
        setLastSearchedQuery(query);

        try {
            const token = await getToken();
            const headers: Record<string, string> = { 'Content-Type': 'application/json' };
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }

            const res = await fetch('/api/search', {
                method: 'POST',
                headers,
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
                    scan: MOCK_CITATION.scan_json as any || [],
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

    // Prepare Pages for Gallery (Prev + Highlighted + Next)
    const getGalleryPages = (ev: EvidenceItem | null) => {
        if (!ev) return [];

        let pages: { vol: number; page: number; url: string; boxes: Rect[] }[] = [];
        let minPage = ev.page;
        let maxPage = ev.page;
        let vol = ev.vol;
        let highlights: ScanPageHighlight[] = [];

        // Normalize Scan Data
        if (ev.scan) {
            if (Array.isArray(ev.scan) && ev.scan.length > 0 && 'page' in ev.scan[0]) {
                // New Format
                highlights = ev.scan as ScanPageHighlight[];
            } else if (Array.isArray(ev.scan)) {
                // Old Format (Rect[]) - assume current page
                highlights = [{ vol: ev.vol, page: ev.page, boxes: ev.scan as Rect[] }];
            } else {
                // Single Object Rect
                highlights = [{ vol: ev.vol, page: ev.page, boxes: [ev.scan as Rect] }];
            }
        }

        if (highlights.length > 0) {
            minPage = Math.min(...highlights.map(h => h.page));
            maxPage = Math.max(...highlights.map(h => h.page));
            vol = highlights[0].vol; // Assume single volume for now
        }

        // Add Context Pages (One before, One after)
        const startPage = Math.max(1, minPage - 1);
        const endPage = maxPage + 1; // Limit logic?

        for (let p = startPage; p <= endPage; p++) {
            // Find boxes for this page
            const h = highlights.find(x => x.page === p && x.vol === vol);
            pages.push({
                vol: vol,
                page: p,
                url: `/scans/vol${vol}_page${p}_image1.png`,
                boxes: h ? h.boxes : []
            });
        }

        return pages;
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
                <Header />

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
                                    {response.answer.split('\n').map((line, i) => {
                                        // Regex to match [Vol X, p. Y]
                                        const parts = line.split(/(\[Vol \d+, p\. \d+\])/g);
                                        return (
                                            <p key={i} className="mb-2">
                                                {parts.map((part, partIdx) => {
                                                    if (part.match(/^\[Vol \d+, p\. \d+\]$/)) {
                                                        // Find matching evidence
                                                        const match = response.evidence.find(ev => ev.citation === part);
                                                        if (match) {
                                                            return (
                                                                <button
                                                                    key={partIdx}
                                                                    onClick={() => setActiveEvidence(match)}
                                                                    className="text-amber-700 font-bold hover:underline cursor-pointer bg-amber-50 px-1 rounded mx-0.5 border border-amber-200 text-xs align-middle"
                                                                    title="View Source"
                                                                >
                                                                    {part}
                                                                </button>
                                                            );
                                                        }
                                                        return <span key={partIdx} className="text-gray-500 text-xs">{part}</span>;
                                                    }
                                                    return <span key={partIdx}>{part}</span>;
                                                })}
                                            </p>
                                        );
                                    })}
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
                                            {activeEvidence.entities.map((ent, idx) => {
                                                const q = lastSearchedQuery.toLowerCase();
                                                const e = ent.toLowerCase();
                                                // Highlight if query contains entity OR entity contains query
                                                const isMatch = lastSearchedQuery && (e.includes(q) || q.includes(e));
                                                return (
                                                    <span
                                                        key={idx}
                                                        className={`text-xs px-2 py-1 rounded font-semibold border shadow-sm transition-all duration-300
                                                            ${isMatch
                                                                ? 'bg-amber-300 text-amber-900 border-amber-400 ring-2 ring-amber-500/50 scale-105'
                                                                : 'bg-[#EFEBE9] text-[#4E342E] border-[#D7CCC8]'
                                                            }
                                                        `}
                                                    >
                                                        {ent}
                                                    </span>
                                                );
                                            })}
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
                    <ScanGallery
                        pages={getGalleryPages(activeEvidence)}
                        defaultImage={defaultImage}
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
