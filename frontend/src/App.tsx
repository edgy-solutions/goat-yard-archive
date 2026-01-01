import { useState, useEffect, useMemo, useCallback } from 'react';
import ScanGallery from './components/ScanGallery';
import { MOCK_CITATION } from './mock_data';
import Header from './components/Header';
import { useAuth } from '@clerk/clerk-react';
import { usePostHog } from 'posthog-js/react';
import { Toaster, toast } from 'sonner';
import ReportModal from './components/ReportModal';
import ResponseActions from './components/ResponseActions';
import About from './pages/About';
import Contact from './pages/Contact';
import Privacy from './pages/Privacy';
import Terms from './pages/Terms';
import Footer from './components/Footer';
import AnalyticsManager from './components/AnalyticsManager';
import HighlightedContent from './components/HighlightedContent';
import ReactMarkdown from 'react-markdown';

// Palette removed as requested (reverting to single yellow highlight on selection)

// ... (Types omitted for brevity, keeping existing)

// ... (Inside App function component)


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
    sentence_data?: { sentence_id: string; text: string }[];
    lemma?: string;
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
    // Force HMR refresh
    const [response, setResponse] = useState<SearchResponse | null>(null);
    const [activeEvidence, setActiveEvidence] = useState<EvidenceItem | null>(null);
    const { getToken } = useAuth();
    // User hook removed as logic moved to AnalyticsManager
    const posthog = usePostHog();

    // Track the specifically selected citation sentence (e.g. S01)
    const [focusedSentenceId, setFocusedSentenceId] = useState<string | null>(null);
    const [visiblePage, setVisiblePage] = useState<number | null>(null);

    // Handle Deep Linking (e.g. ?view=privacy)
    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const viewParam = params.get('view');
        if (viewParam === 'privacy') setView('privacy');
        if (viewParam === 'terms') setView('terms');
        if (viewParam === 'contact') setView('contact');
    }, []);

    // User Feedback State
    const [reportModalOpen, setReportModalOpen] = useState(false);
    const [reportContext, setReportContext] = useState<{ query: string, evidenceIds: string[] } | null>(null);

    const handleReportOpen = () => {
        setReportContext({
            query: lastSearchedQuery,
            evidenceIds: response?.evidence.map(e => e.chunk_id) || []
        });
        setReportModalOpen(true);
    };

    const handleReportSubmit = (issueType: string, description: string) => {
        posthog.capture('user_feedback_submitted', {
            issue_type: issueType,
            description: description,
            user_query: reportContext?.query,
            retrieved_chunk_ids: reportContext?.evidenceIds,
            $set: { has_reported_issue: true }
        });
        toast.success("Report submitted. Thank you for helping improve the library.");
    };

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
        setFocusedSentenceId(null);
        setShowMobileGallery(false);
        setLastSearchedQuery(query);

        // Track Search Event
        posthog.capture('search_performed', {
            query_length: query.length,
            is_paid_user: false // TODO: Check actual status if available
        });

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
                // Try to parse JSON error first (especially for 429)
                let errorMsg = `Server Error: ${res.status}`;
                try {
                    const errorJson = await res.json();
                    if (errorJson.detail) {
                        errorMsg = errorJson.detail;
                    }
                } catch (e) {
                    // Fallback to text if not JSON
                    const errText = await res.text();
                    if (errText) errorMsg += ` ${errText}`;
                }

                // Throw with specific flag if 429
                if (res.status === 429) {
                    const err = new Error(errorMsg);
                    (err as any).isRateLimit = true;
                    throw err;
                }
                throw new Error(errorMsg);
            }

            const data = await res.json();
            setResponse(data);

            // Only show evidence if there are actual citations or if the answer DOESN'T indicate failure
            // If citations are empty, it usually means "I regret..." or "No info found"
            if (data.evidence && data.evidence.length > 0 && data.citations && data.citations.length > 0) {
                setActiveEvidence(data.evidence[0]);
            } else {
                setActiveEvidence(null);
            }
        } catch (err) {
            console.error("Search failed:", err);
            const message = err instanceof Error ? err.message : "Unknown error";
            setError(message);

            // Skip mock fallback for Rate Limits
            if ((err as any).isRateLimit) {
                setLoading(false);
                return;
            }

            console.log("Falling back to mock data...");
            // MOCK FALLBACK for other errors
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

    // Mobile State
    const [showMobileGallery, setShowMobileGallery] = useState(false);

    // Navigation State
    const [view, setView] = useState<'chat' | 'about' | 'contact' | 'privacy' | 'terms'>('chat');

    // Dynamic Book Availability
    const [availableBooks, setAvailableBooks] = useState<string[]>([]);

    // Fetch books on mount
    useEffect(() => {
        fetch('/api/books')
            .then(res => res.json())
            .then(data => setAvailableBooks(data.books))
            .catch(err => console.error("Failed to fetch books:", err));
    }, []);

    const handleCitationClick = (evidence: EvidenceItem, sentenceId?: string) => {
        setActiveEvidence(evidence);
        // If a specific sentence ID is provided (from clicking a [Sxx] button), focus it.
        // If undefined (generic click), clear focus so nothing is highlighted.
        setFocusedSentenceId(sentenceId || null);
        setShowMobileGallery(true);
    };

    // Close overlays
    const closeOverlay = () => setView('chat');

    // Memoize the pages so we don't re-trigger ScanGallery's auto-scroll on every render (like when visiblePage updates)
    const galleryPages = useMemo(() => getGalleryPages(activeEvidence), [activeEvidence]);

    // Memoize dimensions to avoid recreating object on every render
    const originalDims = useMemo(() => getOriginalDims(activeEvidence), [activeEvidence]);

    // Stable handler for visibility changes
    // useCallback ensures this function reference doesn't change unless dependencies do
    const handleVisiblePageChange = useCallback((p: number) => {
        setVisiblePage(p);
    }, []);

    return (
        <div className="flex h-[100dvh] overflow-hidden font-serif bg-cream text-coffee relative selection:bg-[#E6D5B8] selection:text-[#2C241B]">
            <Toaster position="top-center" richColors />
            <AnalyticsManager />

            <ReportModal
                isOpen={reportModalOpen}
                onClose={() => setReportModalOpen(false)}
                onSubmit={handleReportSubmit}
            />

            {/* Modal Backdrop & Container */}
            {(view === 'about' || view === 'contact' || view === 'privacy' || view === 'terms') && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center bg-[#2C241B]/40 backdrop-blur-sm p-4 animate-in fade-in duration-200">
                    <div className="w-full max-w-4xl max-h-[85vh] overflow-hidden rounded-xl shadow-2xl border border-[#D7CCC8] bg-[#FDFBF7] animate-in zoom-in-95 duration-200 flex flex-col">
                        <div className="flex-1 overflow-y-auto custom-scrollbar">
                            {view === 'about' && <About onClose={closeOverlay} />}
                            {view === 'contact' && <Contact onClose={closeOverlay} />}
                            {view === 'privacy' && <Privacy onClose={closeOverlay} onOpenContact={() => setView('contact')} />}
                            {view === 'terms' && <Terms onClose={closeOverlay} />}
                        </div>
                    </div>
                </div>
            )}

            {/* Left Pane: Chat & Context */}
            <div className={`w-full md:w-1/2 flex flex-col border-r border-[#E5E0D8] z-10 bg-cream relative
                ${showMobileGallery ? 'hidden md:flex' : 'flex'}
            `}>

                {/* Header - Minimalist */}
                <Header
                    onOpenAbout={() => setView('about')}
                    onOpenContact={() => setView('contact')}
                />

                {/* Main Content Area - no scroll, evidence section has its own scroll */}
                <div className="flex-1 overflow-hidden p-4 md:p-8 space-y-8 flex flex-col">

                    {/* Empty State */}
                    {!response && !loading && !error && (
                        <div className="flex-1 flex flex-col items-center justify-center text-center opacity-60 mt-10">
                            <div className="text-4xl text-[#D7CCC8] mb-4">❦</div>
                            <h2 className="text-xl font-bold text-[#5D4037] mb-2 font-display italic">The Library is Open</h2>
                            <p className="text-sm text-[#8D6E63] max-w-xs mx-auto mb-8 font-ui">
                                Ask Dr. Gill a question about scripture, theology, or the history of redemption.
                            </p>

                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 w-full max-w-4xl px-4">
                                {[
                                    { q: "Who is the Angel of the Lord?", label: "Theology" },
                                    { q: "Explain the Covenant of Grace.", label: "Covenant" },
                                    { q: "What is Justification?", label: "Doctrine" }
                                ].map((item) => (
                                    <button
                                        key={item.q}
                                        onClick={() => { setQuery(item.q); handleSearch(); }}
                                        className="bg-white border border-[#E5E0D8] p-6 rounded-xl text-[#5D4037] hover:bg-[#FAF9F5] hover:border-[#D7CCC8] hover:shadow-md transition-all text-left group h-full flex flex-col justify-between shadow-[0_2px_8px_-2px_rgba(0,0,0,0.05)]"
                                    >
                                        <div>
                                            <span className="text-[10px] uppercase tracking-widest font-ui text-[#A1887F] mb-2 block">{item.label}</span>
                                            <span className="font-serif font-medium text-lg leading-snug block">{item.q}</span>
                                        </div>
                                        <div className="mt-4 flex justify-end">
                                            <span className="text-[#D7CCC8] group-hover:text-[#8D6E63] transition-colors">→</span>
                                        </div>
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Error Banner */}
                    {error && (
                        <div className="bg-red-50/50 border-l-4 border-red-800/50 text-red-900 p-4 rounded-r shadow-sm text-sm backdrop-blur-sm">
                            {(error.includes("My dear friend") || error.includes("Scriptures"))
                                ? <span className="italic font-serif text-[#5D4037]">{error}</span>
                                : <><strong>Connection Error:</strong> {error}</>
                            }
                            {!error.includes("My dear friend") && (
                                <div className="text-xs mt-1 text-red-700 font-ui uppercase tracking-wide">Offline Mode: Using Mock Data</div>
                            )}
                        </div>
                    )}

                    {/* Loading State */}
                    {loading && (
                        <div className="flex items-center justify-center py-10 space-x-3 text-[#8D6E63] animate-pulse">
                            <div className="w-1.5 h-1.5 bg-[#8D6E63] rounded-full animate-bounce" style={{ animationDelay: '0s' }}></div>
                            <div className="w-1.5 h-1.5 bg-[#8D6E63] rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                            <div className="w-1.5 h-1.5 bg-[#8D6E63] rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                            <span className="text-xs font-medium uppercase tracking-widest font-ui">Consulting the Expositor...</span>
                        </div>
                    )}

                    {response && (
                        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                            {/* Answer Card */}
                            <div className="relative">
                                {/* Decorative Quote */}
                                <div className="absolute -top-4 -left-2 text-6xl text-[#E5E0D8] font-serif pointer-events-none">“</div>

                                <div className="relative z-10">
                                    <div className="flex justify-end mb-2">
                                        {response.verified ? (
                                            <span className="flex items-center text-[10px] text-green-800 bg-green-50/80 px-2 py-1 rounded-full border border-green-100 font-bold uppercase tracking-wider font-ui backdrop-blur-sm">
                                                ✓ Verified Source
                                            </span>
                                        ) : (
                                            <span className="text-[10px] text-amber-800 bg-amber-50 px-2 py-1 rounded-full border border-amber-200 font-ui uppercase tracking-wider">
                                                ⚠️ Unverified
                                            </span>
                                        )}
                                    </div>
                                    <div className="prose prose-lg max-w-none text-[#2C241B] leading-relaxed font-serif">
                                        {response.answer.split('\n').map((line, i) => {
                                            const parts = line.split(/(\[[A-Z0-9_, ]+\])/g);
                                            return (
                                                <div key={i} className="mb-4">
                                                    {parts.map((part, partIdx) => {
                                                        if (part.match(/^\[[A-Z0-9_, ]+\]$/)) {
                                                            const rawContent = part.replace(/^\[+|\]+$/g, '');
                                                            const ids = rawContent.split(',').map(s => s.trim()).filter(Boolean);
                                                            const hasMatch = ids.some(id => response.evidence.find(ev =>
                                                                ev.sentence_data?.some(s => s.sentence_id === id)
                                                            ));

                                                            if (hasMatch) {
                                                                return (
                                                                    <span key={partIdx} className="inline-flex flex-wrap gap-1 align-baseline mx-1">
                                                                        {ids.map((id, idIdx) => {
                                                                            const match = response.evidence.find(ev =>
                                                                                ev.sentence_data?.some(s => s.sentence_id === id)
                                                                            );

                                                                            if (match) {
                                                                                const isFocused = focusedSentenceId === id;
                                                                                return (
                                                                                    <button
                                                                                        key={`${partIdx}-${idIdx}`}
                                                                                        onClick={() => handleCitationClick(match, id)}
                                                                                        className={`font-bold cursor-pointer px-2 py-1 rounded-md text-[10px] transition-all font-ui tracking-wide no-underline
                                                                                            ${isFocused
                                                                                                ? 'bg-[#D7CCC8] text-[#2C241B] shadow-sm'
                                                                                                : 'bg-[#EDE0D4] text-[#5D4037] hover:bg-[#D7CCC8] hover:shadow-sm'
                                                                                            }
                                                                                        `}
                                                                                        title={`View Source: ${match.verse_ref || match.citation}`}
                                                                                    >
                                                                                        {match.verse_ref ? match.verse_ref.toUpperCase() : id}
                                                                                    </button>
                                                                                );
                                                                            }
                                                                            return null;
                                                                        })}
                                                                    </span>
                                                                );
                                                            }
                                                            return null;
                                                        }
                                                        // Use ReactMarkdown for text parts to render italics/bold
                                                        // Use span as wrapper to stay inline, but ReactMarkdown defaults to p/div blocks,
                                                        // so we need to process it to allow inline rendering or just accept block behavior?
                                                        // Actually, 'prose' handles paragraphs well. Let's try rendering inline components.
                                                        return (
                                                            <span key={partIdx}>
                                                                <ReactMarkdown
                                                                    components={{
                                                                        p: ({ node, ...props }) => <span {...props} />,
                                                                        a: ({ node, ...props }) => <span className="text-amber-800 underline" {...props} />
                                                                    }}
                                                                >
                                                                    {part}
                                                                </ReactMarkdown>
                                                            </span>
                                                        );
                                                    })}
                                                </div>
                                            );
                                        })}
                                    </div>

                                    <div className="mt-4 flex justify-end">
                                        <ResponseActions
                                            responseId={lastSearchedQuery}
                                            onReport={handleReportOpen}
                                        />
                                    </div>
                                </div>
                            </div>

                            {/* Active Context Snippet - pb-44 ensures text can scroll above floating search bar */}
                            {activeEvidence && (
                                <div className="mt-8 pt-6 pb-44 border-t border-[#E5E0D8]">
                                    <div className="flex justify-between items-center mb-4">
                                        <h3 className="text-xs font-bold uppercase text-[#8D6E63] tracking-widest font-ui flex items-center gap-2">
                                            <span className="w-1.5 h-1.5 bg-[#8D6E63] rounded-full"></span>
                                            Primary Source Evidence
                                            {activeEvidence.citation && (
                                                <span className="text-[#A1887F] font-normal normal-case tracking-normal ml-1">
                                                    {activeEvidence.citation}
                                                </span>
                                            )}
                                        </h3>
                                        {/* Mobile: View Scan Button */}
                                        <button
                                            onClick={() => setShowMobileGallery(true)}
                                            className="md:hidden text-xs bg-[#FFFDF5] text-[#5D4037] border border-[#D7CCC8] px-3 py-1 rounded-full font-ui shadow-sm"
                                        >
                                            View Original Scan →
                                        </button>
                                    </div>
                                    {/* Evidence content with independent scroll - pb-40 provides scroll room past search bar */}
                                    <div id="evidence-scroll-container" className="p-6 pb-40 bg-white rounded-xl shadow-[0_2px_8px_-2px_rgba(0,0,0,0.05)] border border-[#E5E0D8] text-sm text-[#3E2723] font-serif leading-relaxed relative overflow-y-auto max-h-[50vh] custom-scrollbar group">
                                        {/* Paper texture overlay hint */}
                                        <div className="absolute inset-0 bg-[#FDFBF7] opacity-50 pointer-events-none mix-blend-multiply"></div>

                                        <div className="relative z-10">
                                            {/* Highlighted Commentary Content */}
                                            <HighlightedContent
                                                content={activeEvidence.content}
                                                sentenceData={activeEvidence.sentence_data}
                                                citations={response.citations}
                                                lemma={activeEvidence.lemma}
                                                verseRef={activeEvidence.verse_ref}
                                                activeIds={focusedSentenceId ? [focusedSentenceId] : []}
                                                footnotes={activeEvidence.footnotes}
                                            />

                                            {/* Footnotes Display */}
                                            {(() => {
                                                if (!activeEvidence.footnotes || activeEvidence.footnotes.length === 0) return null;

                                                // 1. Identify which footnotes are actually present in the text
                                                // Check both content and sentence_data (in case footnotes are in individual sentences)
                                                let textToSearch = activeEvidence.content || "";
                                                if (activeEvidence.sentence_data) {
                                                    textToSearch += " " + activeEvidence.sentence_data.map((s: { text?: string }) => s.text || "").join(" ");
                                                }

                                                const matches = textToSearch.matchAll(/\[\^(\d+)\]/g);
                                                const activeIDs = new Set<string>();
                                                for (const m of matches) {
                                                    activeIDs.add(m[1]);
                                                }

                                                console.log("Footnote Debug:", {
                                                    contentPreview: textToSearch.slice(0, 200),
                                                    activeIDs: Array.from(activeIDs),
                                                    footnotes: activeEvidence.footnotes
                                                });

                                                if (activeIDs.size === 0) return null;

                                                return (
                                                    <div className="mt-6 pt-4 border-t border-[#E5E0D8] text-xs">
                                                        <h4 className="font-bold text-[#8D6E63] uppercase mb-2 font-ui tracking-wider text-[10px]">Original Footnotes</h4>
                                                        <ul className="space-y-2 text-[#5D4037]/80">
                                                            {activeEvidence.footnotes.map((fn, idx) => {
                                                                // Extract ID from "[10] content..."
                                                                const match = fn.match(/^\[(\d+)\]/);
                                                                if (!match) return null;

                                                                const id = match[1];
                                                                if (!activeIDs.has(id)) return null;

                                                                return (
                                                                    <li id={`footnote-${id}`} key={idx} className="flex gap-2">
                                                                        <span className="opacity-80 leading-relaxed font-serif text-xs">{fn}</span>
                                                                    </li>
                                                                );
                                                            })}
                                                        </ul>
                                                    </div>
                                                );
                                            })()}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                </div>

                {/* Floating Search Bar - with gradient fade backdrop */}
                <div className="absolute bottom-0 left-0 right-0 pointer-events-none z-20">
                    {/* Gradient fade mask to hide text scrolling behind */}
                    <div className="h-24 bg-gradient-to-t from-[#FAF9F5] via-[#FAF9F5]/80 to-transparent pointer-events-none"></div>

                    <div className="bg-[#FAF9F5] pb-6 px-4 md:px-6">
                        <div className="max-w-3xl mx-auto shadow-[0_20px_40px_-12px_rgba(0,0,0,0.15)] rounded-full bg-white border border-[#E5E0D8]/50 p-1.5 flex items-center transition-all hover:shadow-[0_25px_50px_-12px_rgba(0,0,0,0.2)] pointer-events-auto ring-1 ring-[#E5E0D8]/50">
                            <input
                                className="flex-1 px-4 py-2 bg-transparent text-[#2C241B] placeholder-[#A1887F] focus:outline-none font-ui text-sm sm:text-base leading-relaxed"
                                placeholder="Ask a question..."
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                            />
                            <button
                                onClick={handleSearch}
                                disabled={loading}
                                className="bg-[#2C241B] text-[#E6D5B8] px-6 py-2 rounded-full font-medium text-sm hover:bg-[#3E3226] disabled:opacity-50 transition-colors font-ui tracking-wide shadow-sm"
                            >
                                Search
                            </button>
                        </div>

                        {/* Available Books - Discreet Bottom Label */}
                        <div className="text-center mt-3">
                            <span className="text-[10px] text-[#A1887F] font-ui tracking-wide">
                                {availableBooks.length > 0 ? `Library Index: ${availableBooks.join(", ")}` : "Indexing Library..."}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Right Pane: Scan Verification */}
            <div className={`w-full md:w-1/2 bg-[#1A1410] relative border-l border-[#2C241B] flex flex-col
                ${showMobileGallery ? 'flex fixed inset-0 z-50 md:static md:flex' : 'hidden md:flex'}
            `}>

                {/* Mobile Back Button */}
                <button
                    onClick={() => setShowMobileGallery(false)}
                    className="md:hidden absolute top-4 left-4 z-[60] bg-white/10 backdrop-blur-md text-[#E6D5B8] px-4 py-2 rounded-full border border-white/20 font-ui text-sm flex items-center gap-2"
                >
                    ← Back to Chat
                </button>

                {/* Scan Area */}
                <div className="w-full flex-1 relative min-h-0 bg-[#1A1410] flex flex-col justify-center">
                    <ScanGallery
                        pages={galleryPages}
                        defaultImage={defaultImage}
                        originalDims={originalDims}
                        onVisiblePageChange={handleVisiblePageChange}
                    />

                    {/* Minimalist Overlay Label (Splash Only) */}
                    {!activeEvidence && (
                        <div className="absolute top-6 right-6 pointer-events-none z-10 text-right">
                            <div className="text-[#E6D5B8] text-sm font-serif italic tracking-wider opacity-80">
                                Dr. John Gill
                            </div>
                            <div className="text-white font-ui font-bold text-lg tracking-widest uppercase opacity-90">
                                Exposition of the Bible
                            </div>
                        </div>
                    )}

                    {/* Active Page Overlay */}
                    {activeEvidence && (
                        <div className="absolute top-6 right-6 pointer-events-none z-10 text-right">
                            <div className="text-[#8D6E63] text-sm font-ui tracking-wide uppercase bg-[#1A1410]/80 px-3 py-1 rounded-full backdrop-blur-sm border border-[#8D6E63]/30 shadow-sm text-white/90">
                                Vol. {activeEvidence.vol} — Page {visiblePage || activeEvidence.page}
                            </div>
                        </div>
                    )}
                </div>

                <div className="absolute bottom-0 w-full z-20 bg-gradient-to-t from-[#15100D] via-[#15100D]/90 to-transparent pt-12 pb-2">
                    <Footer onOpenPrivacy={() => setView('privacy')} onOpenTerms={() => setView('terms')} />
                </div>
            </div>

        </div >
    );
}

export default App;
