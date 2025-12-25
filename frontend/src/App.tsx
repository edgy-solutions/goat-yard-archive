
import React, { useState } from 'react';
import ScanViewer from './components/ScanViewer';
import { MOCK_CITATION } from './mock_data';

// Types (should actully be in types.ts but putting here for single-file portability if needed)
interface EvidenceItem {
    chunk_id: string;
    content: string;
    verse_ref?: string;
    citation: string;
    vol: number;
    page: number;
    scan: { x: number; y: number; w: number; h: number } | null;
    score: number;
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
                body: JSON.stringify({ query })
            });

            if (!res.ok) throw new Error("API call failed");

            const data: SearchResponse = await res.json();
            setResponse(data);

            // Auto-select first evidence if available
            if (data.evidence.length > 0) {
                setActiveEvidence(data.evidence[0]);
            }

        } catch (err) {
            console.error(err);
            setError("Backend unavailable. Showing Mock Mode.");
            // Fallback to Mock
            const mockEv = {
                chunk_id: "mock1",
                content: MOCK_CITATION.text,
                citation: "[Vol 1, p. 287]",
                vol: 1,
                page: 287,
                scan: MOCK_CITATION.scan_json,
                score: 1.0
            };
            setResponse({
                answer: "This is a mock response because the backend is not connected. " + MOCK_CITATION.text,
                citations: ["[Vol 1, p. 287]"],
                evidence: [mockEv],
                verified: true
            });
            setActiveEvidence(mockEv);
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
        return { w: 2500, h: 3800 }; // Standard size for now
    };

    return (
        <div className="flex h-screen bg-white font-sans text-gray-800">

            {/* Left Pane: Chat & Context */}
            <div className="w-1/2 flex flex-col border-r border-gray-200">

                {/* Header */}
                <div className="p-4 border-b bg-gray-50">
                    <h1 className="text-xl font-bold text-blue-900">Dr. Gill's Assistant</h1>
                    <p className="text-xs text-gray-500">Grounded Theological AI</p>
                </div>

                {/* Chat / Content Area */}
                <div className="flex-1 overflow-auto p-6 space-y-6">
                    {/* User Query Input (if empty state) */}
                    {!response && !loading && (
                        <div className="text-center mt-20 text-gray-400">
                            <p>Ask a question about the Scriptures or Theology.</p>
                        </div>
                    )}

                    {loading && <div className="text-center text-blue-500">Searching the Archives...</div>}

                    {response && (
                        <div className="space-y-4">
                            {/* Answer */}
                            <div className="bg-blue-50 p-4 rounded-lg relative">
                                <div className="prose max-w-none">
                                    <p>{response.answer}</p>
                                </div>
                                {response.verified ? (
                                    <span className="absolute top-2 right-2 flex items-center text-xs text-green-700 bg-green-100 px-2 py-1 rounded-full">
                                        ✓ Verified
                                    </span>
                                ) : (
                                    <span className="absolute top-2 right-2 text-xs text-red-700 bg-red-100 px-2 py-1 rounded-full text-center">
                                        ⚠ Unverified
                                    </span>
                                )}
                            </div>

                            {/* Citations Buttons */}
                            <div className="flex flex-wrap gap-2">
                                {response.evidence.map((ev) => (
                                    <button
                                        key={ev.chunk_id}
                                        onClick={() => setActiveEvidence(ev)}
                                        className={`px-3 py-1 rounded text-sm border transition-colors
                                    ${activeEvidence?.chunk_id === ev.chunk_id
                                                ? 'bg-blue-600 text-white border-blue-600'
                                                : 'bg-white text-blue-600 border-blue-200 hover:bg-blue-50'}
                                `}
                                    >
                                        {ev.citation}
                                    </button>
                                ))}
                            </div>

                            {/* Active Context Snippet */}
                            {activeEvidence && (
                                <div className="mt-6 border-t pt-4">
                                    <h3 className="text-sm font-bold uppercase text-gray-500 mb-2">
                                        Evidence Source: {activeEvidence.verse_ref || "Unknown Verse"}
                                    </h3>
                                    <div className="p-3 bg-gray-50 border rounded text-sm text-gray-700">
                                        {activeEvidence.content}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Input Area */}
                <div className="p-4 border-t bg-white">
                    <div className="flex gap-2">
                        <input
                            className="flex-1 p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                            placeholder="e.g. What does he say about the covenant of grace?"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                        />
                        <button
                            onClick={handleSearch}
                            disabled={loading}
                            className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
                        >
                            Search
                        </button>
                    </div>
                </div>
            </div>

            {/* Right Pane: Scan Verification */}
            <div className="w-1/2 bg-gray-100 relative">
                <ScanViewer
                    imageUrl={activeEvidence ? getImageUrl(activeEvidence) : ""}
                    highlightBox={activeEvidence?.scan || null}
                    originalDims={getOriginalDims(activeEvidence)}
                />

                {/* Verification Overlay Label */}
                <div className="absolute top-4 left-4 bg-black/70 text-white px-3 py-1 rounded text-sm pointer-events-none">
                    Original Scan {activeEvidence ? `(Vol ${activeEvidence.vol}, p. ${activeEvidence.page})` : ""}
                </div>
            </div>

        </div>
    );
}

export default App;
