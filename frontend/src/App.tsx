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
import { TopicMatrixSidebar } from './components/TopicMatrixSidebar';

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
    const [isMatrixOpen, setIsMatrixOpen] = useState(false);

    const [history, setHistory] = useState<{query: string, created_at: string}[]>([]);
    const [isHistoryOpen, setIsHistoryOpen] = useState(false);

    const fetchHistory = async () => {
        try {
            const token = await getToken();
            const headers: Record<string, string> = { 'Content-Type': 'application/json' };
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            const res = await fetch('/api/history', { headers });
            if (res.ok) {
                const data = await res.json();
                setHistory(data);
            }
        } catch (err) {
            console.error("Failed to fetch history:", err);
        }
    };

    useEffect(() => {
        fetchHistory();
    }, []);

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

    const fetchSingleChunk = async (chunkId: string) => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch(`/api/chunk/${chunkId}`);
            if (!res.ok) throw new Error("Failed to fetch chunk");
            const data: EvidenceItem = await res.json();
            
            // Set the response state so the UI displays the chunk correctly
            setResponse({
                answer: `Showing excerpt from ${data.citation || data.verse_ref || 'Commentary'}`,
                citations: [data.citation || data.verse_ref || ''],
                evidence: [data],
                verified: true
            });
            setActiveEvidence(data);
            setLastSearchedQuery("");
        } catch (err: any) {
            console.error(err);
            setError(err.message || "Failed to fetch specific chunk");
        } finally {
            setLoading(false);
        }
    };

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
        setQuery("");

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
            fetchHistory();
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

    const handleCitationClick = (evidence: EvidenceItem, sentenceId?: string, event?: React.MouseEvent) => {
        setActiveEvidence(evidence);
        // If a specific sentence ID is provided (from clicking a [Sxx] button), focus it.
        // If undefined (generic click), clear focus so nothing is highlighted.
        setFocusedSentenceId(sentenceId || null);
        // Don't auto-show gallery on mobile - user must click "View Scan" button
        setShowMobileGallery(false);

        // Mobile-only: Scroll answer pane so clicked verse stays visible near top (~1/4 down)
        // On mobile, the scroll container is .answer-pane-responsive (content-wrapper has overflow:hidden)
        if (window.innerWidth < 768 && event?.currentTarget) {
            const clickedButton = event.currentTarget as HTMLElement;
            const answerPane = document.querySelector('.answer-pane-responsive') as HTMLElement;

            if (answerPane) {
                // Position clicked verse near top of pane - leave only ~60px (2-3 sentences) above
                // This gives more room for the evidence pane below
                const targetOffset = 60; // Fixed offset in pixels for minimal context above
                const buttonRect = clickedButton.getBoundingClientRect();
                const paneRect = answerPane.getBoundingClientRect();
                const relativeButtonTop = buttonRect.top - paneRect.top + answerPane.scrollTop;

                // Scroll so button is near top with small offset
                const scrollTarget = relativeButtonTop - targetOffset;

                // Delay slightly to let React re-render with new activeEvidence
                setTimeout(() => {
                    answerPane.scrollTo({
                        top: Math.max(0, scrollTarget),
                        behavior: 'smooth'
                    });
                }, 100);
            }
        }
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

            {/* Topic Matrix Sidebar — inline left panel on desktop */}
            <TopicMatrixSidebar
                isOpen={isMatrixOpen}
                onClose={() => setIsMatrixOpen(false)}
                query={lastSearchedQuery || query}
                onCitationClick={fetchSingleChunk}
            />

            {/* Left Pane: Chat & Context */}
            <div className={`flex-1 flex flex-col border-r border-[#E5E0D8] z-10 bg-cream relative
                ${showMobileGallery ? 'hidden md:flex' : 'flex'}
            `}>

                {/* Header - Minimalist */}
                <Header
                    onOpenAbout={() => setView('about')}
                    onOpenContact={() => setView('contact')}
                />

                {/* Main Content Area - 50/50 split, with padding for search bar */}
                <div className="content-wrapper-responsive flex-1 p-4 md:p-8 pb-24 flex flex-col">

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
                                    { q: "What does Gill say about the Word of God?", label: "Theology" },
                                    { q: "What does Gill say about baptism?", label: "Ecclesiology" },
                                    { q: "What does Gill say about the Garden?", label: "Genesis" }
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
                        <div className="answer-pane-responsive animate-in fade-in slide-in-from-bottom-4 duration-500 custom-scrollbar">
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
                                                                                        onClick={(e) => handleCitationClick(match, id, e)}
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
                        </div>
                    )}

                    {/* Active Context Snippet - responsive: mobile=fixed bottom pane, desktop=inline */}
                    {response && activeEvidence && (
                        <div className="evidence-pane-responsive">
                            <div className="evidence-pane-header">
                                <h3 className="text-xs font-bold uppercase text-[#8D6E63] tracking-widest font-ui flex items-center gap-2">
                                    <span className="w-1.5 h-1.5 bg-[#8D6E63] rounded-full"></span>
                                    Primary Source Evidence
                                    {activeEvidence.citation && (
                                        <span className="text-[#A1887F] font-normal normal-case tracking-normal ml-1 hidden sm:inline">
                                            {activeEvidence.citation}
                                        </span>
                                    )}
                                </h3>
                                {/* Mobile: View Scan Button */}
                                <button
                                    onClick={() => setShowMobileGallery(true)}
                                    className="md:hidden text-xs bg-white text-[#5D4037] border border-[#D7CCC8] px-3 py-1 rounded-full font-ui shadow-sm whitespace-nowrap"
                                >
                                    View Scan →
                                </button>
                            </div>
                            {/* Evidence content */}
                            <div id="evidence-scroll-container" className="evidence-pane-content text-sm text-[#3E2723] font-serif leading-relaxed relative custom-scrollbar group">
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

                                        let textToSearch = activeEvidence.content || "";
                                        if (activeEvidence.sentence_data) {
                                            textToSearch += " " + activeEvidence.sentence_data.map((s: { text?: string }) => s.text || "").join(" ");
                                        }

                                        const matches = textToSearch.matchAll(/\[\^(\d+)\]/g);
                                        const activeIDs = new Set<string>();
                                        for (const m of matches) {
                                            activeIDs.add(m[1]);
                                        }

                                        if (activeIDs.size === 0) return null;

                                        return (
                                            <div className="mt-6 pt-4 border-t border-[#E5E0D8] text-xs">
                                                <h4 className="font-bold text-[#8D6E63] uppercase mb-2 font-ui tracking-wider text-[10px]">Original Footnotes</h4>
                                                <ul className="space-y-2 text-[#5D4037]/80">
                                                    {activeEvidence.footnotes.map((fn, idx) => {
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

                {/* Floating Search Bar - with gradient fade backdrop */}
                <div className="absolute bottom-0 left-0 right-0 pointer-events-none z-20">
                    {/* Minimal gradient fade - just enough to blend search bar edge */}
                    <div className="h-4 md:h-6 bg-gradient-to-t from-[#FAF9F5] to-transparent pointer-events-none"></div>

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
                                onClick={() => setIsMatrixOpen(!isMatrixOpen)}
                                className={`flex items-center gap-2.5 px-4 py-2 rounded-full transition-all duration-300 group/toggle mr-2
                                    ${isMatrixOpen
                                        ? 'bg-[#eae4d8] text-[#2c241b]'
                                        : 'hover:bg-[#f4efe6] text-[#8c7e71] hover:text-[#4a3f35]'
                                    }
                                `}
                                title="Toggle Search Matrix"
                            >
                                <svg
                                    xmlns="http://www.w3.org/2000/svg"
                                    width="18"
                                    height="18"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="1.5"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    className={`transition-transform duration-300 ${isMatrixOpen ? 'scale-105' : 'group-hover/toggle:scale-105'}`}
                                >
                                    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
                                    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
                                    <line x1="6" y1="8" x2="6" y2="14" stroke="currentColor" strokeWidth="1" className="opacity-40" />
                                    <line x1="18" y1="8" x2="18" y2="14" stroke="currentColor" strokeWidth="1" className="opacity-40" />
                                </svg>
                                <span className="font-serif italic text-[15px] tracking-wide pt-[1px]">
                                    Matrix
                                </span>
                            </button>
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

                        {/* Mobile-only: Copyright, Privacy, Terms footer */}
                        <div className="md:hidden mt-2">
                            <Footer variant="main" onOpenPrivacy={() => setView('privacy')} onOpenTerms={() => setView('terms')} />
                        </div>
                    </div>

                    {/* History Drawer Handle */}
                    {history.length > 0 && (
                      <div className="flex justify-center -mt-6 relative z-10 pointer-events-auto">
                        <button 
                          onClick={() => setIsHistoryOpen(!isHistoryOpen)}
                          className="bg-white border border-t-0 border-[#E5E0D8] rounded-b-lg px-6 py-1.5 text-[10px] text-[#A1887F] hover:text-[#5D4037] hover:bg-[#FAF9F5] transition-all font-ui tracking-widest shadow-sm flex items-center gap-2"
                        >
                          {isHistoryOpen ? '▲ Close Ledger' : '▼ Previous Inquiries'}
                        </button>
                      </div>
                    )}

                    {/* History Drawer Content */}
                    {isHistoryOpen && history.length > 0 && (
                      <div className="bg-white border-t border-[#E5E0D8] p-4 max-h-[30vh] overflow-y-auto custom-scrollbar pointer-events-auto shadow-[0_-10px_20px_-10px_rgba(0,0,0,0.05)] animate-in slide-in-from-bottom-2">
                        <div className="max-w-3xl mx-auto">
                          <h4 className="text-[10px] font-bold text-[#8D6E63] uppercase font-ui tracking-wider mb-3">Recent Searches</h4>
                          <div className="flex flex-wrap gap-2">
                            {history.map((item, idx) => (
                              <button
                                key={idx}
                                onClick={() => {
                                  setQuery(item.query);
                                  setIsHistoryOpen(false);
                                  // We use a timeout to let the state update before triggering search
                                  setTimeout(() => handleSearch(), 50); 
                                }}
                                className="bg-[#FAF9F5] border border-[#E5E0D8] text-[#5D4037] px-3 py-1.5 rounded-full text-xs font-serif hover:bg-[#EDE0D4] hover:border-[#D7CCC8] transition-colors shadow-sm text-left"
                              >
                                "{item.query}"
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                </div>
            </div>

            {/* Right Pane: Scan Verification */}
            <div className={`flex-1 bg-[#1A1410] relative border-l border-[#2C241B] flex flex-col
                ${showMobileGallery ? 'flex fixed inset-0 z-50 md:static md:flex' : 'hidden md:flex'}
            `}>

                {/* Mobile Back Button */}
                <button
                    onClick={() => setShowMobileGallery(false)}
                    className="md:hidden absolute top-4 left-4 z-[60] bg-white text-[#2C241B] px-4 py-2 rounded-full border border-[#D7CCC8] font-ui text-sm flex items-center gap-2 shadow-md hover:bg-[#FDFBF7] transition-colors"
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

                <div className="absolute bottom-0 inset-x-0 z-50 flex flex-col">
                    {/* Gradient Fade Only Above Text */}
                    <div className="h-6 bg-gradient-to-t from-[#15100D] to-transparent pointer-events-none"></div>
                    {/* Gallery footer */}
                    <div className="bg-[#15100D] pt-2 pb-4">
                        {/* Mobile: Just powered by / text via */}
                        <div className="md:hidden">
                            <Footer variant="gallery" />
                        </div>
                        {/* Desktop: Full footer with copyright, privacy, terms, powered by, text via */}
                        <div className="hidden md:block">
                            <Footer variant="full" onOpenPrivacy={() => setView('privacy')} onOpenTerms={() => setView('terms')} />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default App;
