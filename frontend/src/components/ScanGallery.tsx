import React, { useEffect, useRef, useState } from 'react';

// Use local interface or import from shared types
interface Rect { x: number; y: number; w: number; h: number; }

export interface GalleryPage {
    vol: number;
    page: number;
    url: string;
    boxes: Rect[];
}

interface ScanGalleryProps {
    pages: GalleryPage[];
    originalDims: { w: number; h: number } | null;
    defaultImage?: string; // Fallback if no pages
    onVisiblePageChange?: (page: number) => void;
}

const ScanPage: React.FC<{ page: GalleryPage; originalDims: { w: number; h: number } | null; shouldFocus?: boolean; onLoaded?: () => void }> = ({ page, originalDims, shouldFocus, onLoaded }) => {
    const imgRef = useRef<HTMLImageElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const scrollAnchorRef = useRef<HTMLDivElement>(null);
    const [loaded, setLoaded] = useState(false);

    // Trigger onLoaded when image loads
    const handleLoad = () => {
        setLoaded(true);
        if (onLoaded) onLoaded();
    };

    // Draw Highlight & Handle Focus
    useEffect(() => {
        if (!loaded || !imgRef.current || !canvasRef.current) return;

        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        // If no highlight boxes, clear
        if (!page.boxes || page.boxes.length === 0) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            return;
        }

        const img = imgRef.current;
        canvas.width = img.clientWidth;
        canvas.height = img.clientHeight;

        const sourceW = (originalDims ? originalDims.w : img.naturalWidth) || 2500;
        const sourceH = (originalDims ? originalDims.h : img.naturalHeight) || 3800;

        const scaleX = img.clientWidth / sourceW;
        const scaleY = img.clientHeight / sourceH;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        page.boxes.forEach(box => {
            const x = box.x * scaleX;
            const y = box.y * scaleY;
            const w = box.w * scaleX;
            const h = box.h * scaleY;

            // Semi-transparent yellow fill
            ctx.fillStyle = 'rgba(255, 255, 0, 0.3)';
            ctx.fillRect(x, y, w, h);

            // Solid border
            ctx.strokeStyle = '#F59E0B';
            ctx.lineWidth = 2;
            ctx.strokeRect(x, y, w, h);
        });

        // Auto-scroll handled by parent now (Global Centering)

    }, [page, originalDims, loaded, shouldFocus]);

    return (
        <div className="relative w-full mb-8 shadow-lg">
            {/* Page Number Label */}
            <div className="absolute -top-6 left-0 text-amber-200/50 text-xs font-serif">
                Page {page.page}
            </div>

            {/* Invisible Scroll Target Anchor */}
            <div ref={scrollAnchorRef} className="absolute left-0 w-1 h-1 pointer-events-none" style={{ top: 0 }} />

            <img
                ref={imgRef}
                src={page.url}
                alt={`Page ${page.page}`}
                className="w-full h-auto block rounded-sm bg-white"
                onLoad={handleLoad}
            />
            <canvas
                ref={canvasRef}
                className={`absolute top-0 left-0 pointer-events-none z-10 transition-opacity duration-300 ${loaded ? 'opacity-100' : 'opacity-0'}`}
            />
        </div>
    );
};

const ScanGallery: React.FC<ScanGalleryProps> = ({ pages, originalDims, defaultImage, onVisiblePageChange }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const [imagesLoaded, setImagesLoaded] = useState<Record<number, boolean>>({});

    // Track image loading state to trigger scroll calculation only when ready
    const handleImageLoad = (pageNum: number) => {
        setImagesLoaded(prev => ({ ...prev, [pageNum]: true }));
    };

    // Track Visible Page on Scroll
    useEffect(() => {
        if (!onVisiblePageChange || pages.length === 0) return;

        const observer = new IntersectionObserver(
            (entries) => {
                // Find visible page(s)
                const visibleEntries = entries.filter(entry => entry.isIntersecting);

                if (visibleEntries.length > 0) {
                    // Sort by visibility ratio if needed, or just take the first one
                    // Taking the one with the largest intersection ratio usually "feels" right
                    const mostVisible = visibleEntries.reduce((prev, current) =>
                        (prev.intersectionRatio > current.intersectionRatio) ? prev : current
                    );

                    // Extract page number from ID
                    const pageId = mostVisible.target.id;
                    const pageNum = parseInt(pageId.replace('gallery-page-', ''), 10);

                    if (!isNaN(pageNum)) {
                        onVisiblePageChange(pageNum);
                    }
                }
            },
            {
                root: containerRef.current,
                threshold: [0.1, 0.5, 0.9] // Multiple thresholds for smoother detection
            }
        );

        pages.forEach(page => {
            const el = document.getElementById(`gallery-page-${page.page}`);
            if (el) observer.observe(el);
        });

        return () => observer.disconnect();
    }, [pages, onVisiblePageChange]);

    // Track if we have performed the initial auto-scroll for this set of pages
    const hasScrolledRef = useRef(false);

    // Reset scroll tracking when pages change
    useEffect(() => {
        hasScrolledRef.current = false;
    }, [pages]);

    // Auto-scroll logic: Global Centering
    useEffect(() => {
        // If we've already scrolled for this evidence set, don't do it again.
        // This effectively stops the "fighting back" behavior on manual scroll.
        if (hasScrolledRef.current) return;

        // Wait for all relevant images to load? Or just the ones with highlights?
        // Let's assume we need layout to be stable.
        const pagesWithHighlights = pages.filter(p => p.boxes.length > 0);
        if (pagesWithHighlights.length === 0) return;

        // Check if relevant pages are loaded
        const allRelevantLoaded = pagesWithHighlights.every(p => imagesLoaded[p.page]);
        if (!allRelevantLoaded) return;

        // Delay slightly for layout paint
        const timeout = setTimeout(() => {
            if (!containerRef.current) return;

            // 1. Calculate Global Bounds
            let globalMinY = Infinity;
            let globalMaxY = -Infinity;
            let validMeasurements = false;

            pagesWithHighlights.forEach(p => {
                const element = document.getElementById(`gallery-page-${p.page}`);
                if (!element) return;

                // Get the image element inside to calculate scale
                const img = element.querySelector('img');
                if (!img) return;

                const pageTop = element.offsetTop;
                const sourceH = (originalDims ? originalDims.h : 3800); // fallback
                const scaleY = img.clientHeight / sourceH;

                p.boxes.forEach(box => {
                    const boxTop = pageTop + (box.y * scaleY);
                    const boxBottom = pageTop + ((box.y + box.h) * scaleY);

                    if (boxTop < globalMinY) globalMinY = boxTop;
                    if (boxBottom > globalMaxY) globalMaxY = boxBottom;
                    validMeasurements = true;
                });
            });

            if (!validMeasurements) return;

            // 2. Determine Scroll Target
            const contentHeight = globalMaxY - globalMinY;
            const viewportHeight = containerRef.current.clientHeight;
            const contentCenter = globalMinY + (contentHeight / 2);

            let targetScroll = 0;

            if (contentHeight > (viewportHeight * 0.9)) {
                // If content is taller than viewport (or close to it), align top
                // Add a little padding (e.g. 20px)
                targetScroll = Math.max(0, globalMinY - 20);
            } else {
                // Center the content block in the viewport
                targetScroll = Math.max(0, contentCenter - (viewportHeight / 2));
            }

            containerRef.current.scrollTo({ top: targetScroll, behavior: 'smooth' });

            // Mark as done so we don't fight the user
            hasScrolledRef.current = true;

        }, 100);

        return () => clearTimeout(timeout);
    }, [pages, imagesLoaded, originalDims]);

    // Unified Render
    return (
        <div className="relative w-full h-full bg-[#1A1410] overflow-hidden">
            {/* 1. Persistent Background Layer */}
            {defaultImage && (
                <div className="absolute inset-0 z-0">
                    <img
                        src={defaultImage}
                        alt="Background"
                        className={`w-full h-full object-cover transition-all duration-700 ${pages.length > 0 ? 'opacity-50' : 'opacity-100'}`}
                    />
                    {/* Dark Overlay only when pages are present to improve readability */}
                    <div className={`absolute inset-0 bg-[#1A1410] mix-blend-multiply transition-opacity duration-700 ${pages.length > 0 ? 'opacity-60' : 'opacity-0'}`}></div>
                </div>
            )}

            {/* 2. Scrollable Content Layer */}
            <div className="relative z-10 w-full h-full overflow-y-auto p-4 custom-scrollbar" ref={containerRef}>
                <div className="w-full mx-auto space-y-12 pb-32 pt-4">
                    {pages.map((page) => (
                        <div id={`gallery-page-${page.page}`} key={page.page} className="flex justify-center relative">
                            <div className="max-w-full">
                                <ScanPage
                                    page={page}
                                    originalDims={originalDims}
                                    shouldFocus={false}
                                    onLoaded={() => handleImageLoad(page.page)}
                                />
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default ScanGallery;
