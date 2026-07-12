import { useState, useEffect, useMemo, useCallback } from 'react';
import ScanGallery from './components/ScanGallery';
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
    // Sentence IDs (bare form, no brackets) whose Gill quote couldn't be
    // verified — paraphrased, KJV-only, or no quote attached at all. Used
    // to apply the warning color + icon to the specific citation pills in
    // the answer, so the user can see WHERE the verification failure is.
    unverified_sentence_ids?: string[];
    // True when the answer contained no inline [SENTENCE_ID] citations,
    // i.e. the bot didn't produce a real verbatim quote (either canned
    // refusal or paraphrase). When true, the UI surfaces the reasoning
    // panel below so the user can see what the model considered.
    refused?: boolean;
    // Model's reasoning text — useful only in the refused=true case to
    // surface what the model identified but chose not to commit to.
    reasoning?: string;
    // Sentence IDs the model named in its reasoning that are real
    // (i.e. exist in the retrieved context). Frontend renders these as
    // clickable amber pills inside the reasoning panel.
    partial_match_sids?: string[];
    trace_id?: string;
}

// The model occasionally produces range-style sentence citations like
// `[MATTHEW_24_45_S02-S04]` to indicate a quote spanning sentences S02
// through S04 of the same verse. Expand to individual sentence IDs so each
// can be rendered as its own citation button (matching the comma-separated
// list path) and matched against retrieved evidence.
function expandSentenceIdRange(id: string): string[] {
    // Pattern: anything ending in `_Saa-Sbb` where aa and bb are zero-padded digits.
    const m = id.match(/^(.+_S)(\d+)-S(\d+)$/);
    if (!m) return [id];
    const [, prefix, startStr, endStr] = m;
    const start = parseInt(startStr, 10);
    const end = parseInt(endStr, 10);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return [id];
    const padTo = startStr.length;
    const result: string[] = [];
    for (let n = start; n <= end; n++) {
        result.push(`${prefix}${String(n).padStart(padTo, '0')}`);
    }
    return result;
}

// Extract every sentence-ID cited in the answer text, using the same
// [SID] bracket + comma-separated + range-expansion logic the citation
// pill renderer uses. Feeds the "which evidence chunk is really primary"
// selection so the UI shows a chunk the answer actually references
// rather than the alphabetically-first retrieved chunk (2026-07-12 fix).
function extractCitedSids(answer: string): Set<string> {
    const sids = new Set<string>();
    const brackets = answer.match(/\[[A-Za-z0-9_, -]+\]/g) || [];
    for (const bracket of brackets) {
        const raw = bracket.replace(/^\[+|\]+$/g, '');
        raw.split(',')
            .map(s => s.trim())
            .filter(Boolean)
            .flatMap(expandSentenceIdRange)
            .forEach(id => sids.add(id));
    }
    return sids;
}

function App() {
    const [query, setQuery] = useState("");
    const [loading, setLoading] = useState(false);
    // Force HMR refresh
    const [response, setResponse] = useState<SearchResponse | null>(null);
    const [activeEvidence, setActiveEvidence] = useState<EvidenceItem | null>(null);
    const [currentTraceId, setCurrentTraceId] = useState<string | null>(null);
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

    const handleReportSubmit = async (issueType: string, description: string) => {
        posthog.capture('user_feedback_submitted', {
            issue_type: issueType,
            description: description,
            user_query: reportContext?.query,
            retrieved_chunk_ids: reportContext?.evidenceIds,
            $set: { has_reported_issue: true }
        });

        // Also send to backend feedback endpoint
        try {
            const token = await getToken();
            const headers: Record<string, string> = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = `Bearer ${token}`;

            await fetch('/api/feedback', {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    trace_id: currentTraceId,
                    score: 0,
                    issue_type: issueType,
                    comment: description
                })
            });
        } catch (e) {
            console.error('Failed to send feedback to backend:', e);
        }

        toast.success("Report submitted. Thank you for helping improve the library.");
    };

    // Track the query that ACTUALLY produced the results, for highlighting
    const [lastSearchedQuery, setLastSearchedQuery] = useState("");

    // Default Image Rotation
    const [defaultImage] = useState(() => {
        const images = ['/scans/gill1.png', '/scans/gill2.png', '/scans/gill3.png'];
        return images[Math.floor(Math.random() * images.length)];
    });

    // Error state. `errorKind` lets the UI render different messaging for
    // backend-down vs rate-limit vs bad-request vs generic.
    const [error, setError] = useState<string | null>(null);
    const [errorKind, setErrorKind] = useState<
        null | 'rate_limit' | 'backend_unavailable' | 'bad_request' | 'other'
    >(null);

    const handleSearch = async () => {
        if (!query) return;
        setLoading(true);
        setError(null);
        setErrorKind(null);
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

        // Per-request timeout so users aren't stuck on a hung backend forever.
        // 90s is generous (the backend itself caps LLM generation at 60s + the
        // BAML+retrieval pipeline can add 10-20s on a cold cache).
        const controller = new AbortController();
        const timeoutId = window.setTimeout(() => controller.abort(), 90_000);

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
                signal: controller.signal,
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

                // Classify based on status code so the UI can render the right
                // tone (rate-limit explanation vs unavailable banner vs generic).
                if (res.status === 429) {
                    setErrorKind('rate_limit');
                    throw new Error(errorMsg);
                }
                if (res.status >= 500) {
                    // 5xx from origin OR Cloudflare's 502 when home is unreachable.
                    setErrorKind('backend_unavailable');
                    throw new Error(errorMsg);
                }
                if (res.status === 404) {
                    // /api/search never legitimately returns 404 — the route is
                    // registered on the backend. When traefik has no healthy api
                    // pods (e.g. mid-rollout, OOMKilled, scaled to 0) it returns
                    // 404 with no matching backend. Treat as backend_unavailable
                    // so the user sees the graceful-degradation message instead
                    // of "bad request".
                    setErrorKind('backend_unavailable');
                    throw new Error(errorMsg);
                }
                if (res.status >= 400) {
                    setErrorKind('bad_request');
                    throw new Error(errorMsg);
                }
                setErrorKind('other');
                throw new Error(errorMsg);
            }

            const data = await res.json();
            setResponse(data);
            setCurrentTraceId(data.trace_id || null);

            // Only show evidence if there are actual citations or if the answer DOESN'T indicate failure
            // If citations are empty, it usually means "I regret..." or "No info found"
            if (data.evidence && data.evidence.length > 0 && data.citations && data.citations.length > 0) {
                // Pick the first evidence chunk whose sentence_data contains
                // a SID actually cited in the answer text. The evidence
                // array isn't sorted by relevance — it can arrive in
                // alphabetical-by-verse-ref order — so evidence[0] often
                // isn't the chunk the model quoted from. The 2026-07-12
                // psalmody incident showed JOHN 3:25 as "primary source
                // evidence" while the answer cited LUKE 15:26; this fixes
                // that class by matching on SID membership instead of
                // array position.
                const citedSids = extractCitedSids(data.answer);
                const firstCited = (data.evidence as EvidenceItem[]).find(
                    (ev: EvidenceItem) => ev.sentence_data?.some(
                        (s: { sentence_id: string }) => s.sentence_id && citedSids.has(s.sentence_id)
                    )
                );
                setActiveEvidence(firstCited || data.evidence[0]);
            } else {
                setActiveEvidence(null);
            }
        } catch (err) {
            console.error("Search failed:", err);

            // Disambiguate transport-layer failures (origin unreachable, DNS
            // failure, TLS error, timeout) from response-layer failures
            // (errors with a parsed status code, handled above).
            if (err instanceof DOMException && err.name === 'AbortError') {
                setErrorKind('backend_unavailable');
                setError("The request timed out. The commentary index may be temporarily unavailable.");
            } else if (err instanceof TypeError) {
                // `fetch` throws TypeError for network errors (origin unreachable,
                // CORS, DNS failure). Cloudflare 502/503 are returned via the
                // status-code path above; this branch is for true network errors.
                setErrorKind('backend_unavailable');
                setError("Unable to reach the commentary index.");
            } else {
                // errorKind was already set above for status-code paths.
                const message = err instanceof Error ? err.message : "Unknown error";
                setError(message);
            }
        } finally {
            window.clearTimeout(timeoutId);
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

            {/* Left Pane: Chat & Context */}
            <div className={`w-full md:w-1/2 flex flex-col border-r border-[#E5E0D8] z-10 bg-cream relative
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
                    {error && errorKind === 'rate_limit' && (
                        <div className="bg-amber-50/50 border-l-4 border-amber-700/50 text-amber-900 p-4 rounded-r shadow-sm text-sm backdrop-blur-sm">
                            <span className="italic font-serif text-[#5D4037]">{error}</span>
                        </div>
                    )}

                    {error && errorKind === 'backend_unavailable' && (
                        <div className="bg-stone-50/70 border-l-4 border-stone-600/60 text-stone-800 p-5 rounded-r shadow-sm backdrop-blur-sm">
                            <h3 className="font-serif text-lg text-[#3E2723] mb-2">The commentary index is temporarily unavailable.</h3>
                            <p className="text-sm leading-relaxed text-stone-700">
                                We're briefly unable to reach the search index. This is usually a short interruption; the site itself is otherwise working normally. Please try your inquiry again in a few minutes.
                            </p>
                            <div className="mt-3 flex flex-wrap items-center gap-3 text-xs font-ui">
                                <button
                                    onClick={() => { setQuery(lastSearchedQuery); handleSearch(); }}
                                    className="px-3 py-1.5 bg-stone-800 text-stone-50 rounded hover:bg-stone-700 transition-colors"
                                >
                                    Retry
                                </button>
                                <a
                                    href="https://github.com/cnogradi/goat-yard-archive"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="underline text-stone-600 hover:text-stone-800"
                                >
                                    Project on GitHub
                                </a>
                            </div>
                            <details className="mt-3 text-xs text-stone-500">
                                <summary className="cursor-pointer hover:text-stone-700">Technical detail</summary>
                                <code className="block mt-1 font-mono text-[10px] break-all">{error}</code>
                            </details>
                        </div>
                    )}

                    {error && (errorKind === 'bad_request' || errorKind === 'other') && (
                        <div className="bg-red-50/50 border-l-4 border-red-800/50 text-red-900 p-4 rounded-r shadow-sm text-sm backdrop-blur-sm">
                            <strong>Error:</strong> {error}
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
                            {/* User's question — echoed back so the reader can see
                                what was asked while reading the answer. Absence of
                                this echo caused confusion on the 2026-07-12 psalmody
                                incident where the answer's off-topic quote sat
                                without any anchor to the original query. */}
                            {lastSearchedQuery && (
                                <div className="mb-6 pb-4 border-b border-[#E5E0D8]">
                                    <div className="text-[10px] uppercase tracking-wider text-[#8D6E63] font-ui mb-1 font-bold">
                                        You asked
                                    </div>
                                    <div className="text-base text-[#5D4037] font-serif italic leading-snug">
                                        {lastSearchedQuery}
                                    </div>
                                </div>
                            )}

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
                                        ) : response.refused && (response.partial_match_sids?.length ?? 0) > 0 ? (
                                            // Refused-but-partial: model didn't quote anything but its
                                            // reasoning identified relevant SIDs. Different shade so users
                                            // know there's nuance below.
                                            <span className="text-[10px] text-amber-900 bg-amber-100 px-2 py-1 rounded-full border border-amber-300 font-ui uppercase tracking-wider">
                                                ⚠️ No Verbatim Quote — Partial Coverage
                                            </span>
                                        ) : (
                                            <span className="text-[10px] text-amber-800 bg-amber-50 px-2 py-1 rounded-full border border-amber-200 font-ui uppercase tracking-wider">
                                                ⚠️ Unverified
                                            </span>
                                        )}
                                    </div>
                                    <div className="prose prose-lg max-w-none text-[#2C241B] leading-relaxed font-serif">
                                        {response.answer.split('\n').map((line, i) => {
                                            // Allow `-` inside the citation pattern so range citations like
                                            // `[MATTHEW_24_45_S02-S04]` are matched (then expanded below).
                                            // Allow lowercase letters because the model occasionally produces
                                            // non-canonical IDs (e.g. `[GENESIS_1_End_S00]`); matching them
                                            // here at least suppresses the raw bracket text from the UI even
                                            // when the ID won't resolve to a real chunk.
                                            const parts = line.split(/(\[[A-Za-z0-9_, -]+\])/g);
                                            return (
                                                <div key={i} className="mb-4">
                                                    {parts.map((part, partIdx) => {
                                                        if (part.match(/^\[[A-Za-z0-9_, -]+\]$/)) {
                                                            const rawContent = part.replace(/^\[+|\]+$/g, '');
                                                            const ids = rawContent
                                                                .split(',')
                                                                .map(s => s.trim())
                                                                .filter(Boolean)
                                                                .flatMap(expandSentenceIdRange);
                                                            const hasMatch = ids.some(id => response.evidence.find(ev =>
                                                                ev.sentence_data?.some(s => s.sentence_id === id)
                                                            ));

                                                            if (hasMatch) {
                                                                const unverifiedSet = new Set(response.unverified_sentence_ids || []);
                                                                return (
                                                                    <span key={partIdx} className="inline-flex flex-wrap gap-1 align-baseline mx-1">
                                                                        {ids.map((id, idIdx) => {
                                                                            const match = response.evidence.find(ev =>
                                                                                ev.sentence_data?.some(s => s.sentence_id === id)
                                                                            );

                                                                            if (match) {
                                                                                const isFocused = focusedSentenceId === id;
                                                                                const isUnverified = unverifiedSet.has(id);
                                                                                // Yellow + ⚠️ matches the "⚠️ Unverified" badge above,
                                                                                // so users can pinpoint WHICH citation failed verification
                                                                                // rather than only seeing a global pill at the top.
                                                                                const pillClass = isUnverified
                                                                                    ? (isFocused
                                                                                        ? 'bg-amber-100 text-amber-900 border border-amber-300 shadow-sm'
                                                                                        : 'bg-amber-50 text-amber-800 border border-amber-200 hover:bg-amber-100 hover:shadow-sm')
                                                                                    : (isFocused
                                                                                        ? 'bg-[#D7CCC8] text-[#2C241B] shadow-sm'
                                                                                        : 'bg-[#EDE0D4] text-[#5D4037] hover:bg-[#D7CCC8] hover:shadow-sm');
                                                                                return (
                                                                                    <button
                                                                                        key={`${partIdx}-${idIdx}`}
                                                                                        onClick={(e) => handleCitationClick(match, id, e)}
                                                                                        className={`font-bold cursor-pointer px-2 py-1 rounded-md text-[10px] transition-all font-ui tracking-wide no-underline ${pillClass}`}
                                                                                        title={isUnverified
                                                                                            ? `Unverified — Gill quote could not be confirmed against ${match.verse_ref || match.citation}`
                                                                                            : `View Source: ${match.verse_ref || match.citation}`
                                                                                        }
                                                                                    >
                                                                                        {isUnverified && <span className="mr-1" aria-hidden="true">⚠️</span>}
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

                                    {/*
                                     * Reasoning panel — shown when the bot refused to produce a
                                     * verbatim quote (refused=true) but its reasoning identified
                                     * Sentence IDs that exist in the retrieved context. The model's
                                     * own hedge often names exactly what it considered; surfacing
                                     * that text plus clickable pills turns an opaque refusal into
                                     * a starting point for the user.
                                     */}
                                    {response.refused && (response.partial_match_sids?.length ?? 0) > 0 && response.reasoning && (
                                        <div className="mt-4 p-4 bg-amber-50/40 border border-amber-200 rounded-lg">
                                            <div className="text-[10px] font-bold uppercase tracking-wider text-amber-900 font-ui mb-2">
                                                What the system reviewed
                                            </div>
                                            <p className="text-xs text-[#5D4037] leading-relaxed font-ui mb-3">
                                                No verbatim quote could be produced for your question.
                                                Below is the model's reasoning over the available
                                                extracts — the cited passages may still be worth your
                                                review.
                                            </p>
                                            <div className="text-sm text-[#3E2723] font-serif italic leading-relaxed">
                                                {response.reasoning.split(/(\[[A-Z0-9_]+_S\d+\])/g).map((part, idx) => {
                                                    const m = part.match(/^\[([A-Z0-9_]+_S\d+)\]$/);
                                                    if (m) {
                                                        const sid = m[1];
                                                        const isPartialMatch = response.partial_match_sids?.includes(sid);
                                                        const ev = response.evidence.find(e =>
                                                            e.sentence_data?.some(s => s.sentence_id === sid)
                                                        );
                                                        if (isPartialMatch && ev) {
                                                            return (
                                                                <button
                                                                    key={idx}
                                                                    onClick={(e) => handleCitationClick(ev, sid, e)}
                                                                    className="inline-flex items-center mx-1 font-bold cursor-pointer px-2 py-0.5 rounded-md text-[10px] not-italic bg-amber-100 text-amber-900 border border-amber-300 hover:bg-amber-200 hover:shadow-sm transition-all font-ui tracking-wide"
                                                                    title={`Open: ${ev.verse_ref || ev.citation}`}
                                                                >
                                                                    <span className="mr-1" aria-hidden="true">⚠️</span>
                                                                    {ev.verse_ref ? ev.verse_ref.toUpperCase() : sid}
                                                                </button>
                                                            );
                                                        }
                                                        // SID not in retrieved context — render as text so the
                                                        // reasoning still reads correctly without a dead button.
                                                        return <span key={idx}>{part}</span>;
                                                    }
                                                    return <span key={idx}>{part}</span>;
                                                })}
                                            </div>
                                        </div>
                                    )}

                                    <div className="mt-4 flex justify-end">
                                        <ResponseActions
                                            responseId={lastSearchedQuery}
                                            traceId={currentTraceId}
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
                </div>
            </div>

            {/* Right Pane: Scan Verification */}
            <div className={`w-full md:w-1/2 bg-[#1A1410] relative border-l border-[#2C241B] flex flex-col
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
