
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
}

const ScanPage: React.FC<{ page: GalleryPage; originalDims: { w: number; h: number } | null; shouldFocus?: boolean }> = ({ page, originalDims, shouldFocus }) => {
    const imgRef = useRef<HTMLImageElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const scrollAnchorRef = useRef<HTMLDivElement>(null);
    const [loaded, setLoaded] = useState(false);

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

        // Auto-Scroll if this is the target page
        if (shouldFocus && page.boxes.length > 0 && scrollAnchorRef.current) {
            const firstBox = page.boxes[0];
            const y = firstBox.y * scaleY;
            const h = firstBox.h * scaleY;

            // Position anchor at center of box
            scrollAnchorRef.current.style.top = `${y + h / 2}px`;

            // Scroll after short delay to allow layout
            setTimeout(() => {
                scrollAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 100);
        }

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
                onLoad={() => setLoaded(true)}
            />
            <canvas
                ref={canvasRef}
                className={`absolute top-0 left-0 pointer-events-none z-10 transition-opacity duration-300 ${loaded ? 'opacity-100' : 'opacity-0'}`}
            />
        </div>
    );
};

const ScanGallery: React.FC<ScanGalleryProps> = ({ pages, originalDims, defaultImage }) => {
    const containerRef = useRef<HTMLDivElement>(null);

    // Find index of first page with boxes for focus
    const targetPageIndex = pages.findIndex(p => p.boxes.length > 0);

    if (pages.length === 0 && defaultImage) {
        return (
            <div className="w-full h-full flex items-center justify-center p-8">
                <img src={defaultImage} alt="Placeholder" className="max-w-full shadow-xl opacity-80" />
            </div>
        );
    }

    return (
        <div className="relative w-full h-full overflow-y-auto bg-[#2D1B18] p-2" ref={containerRef}>
            <div className="w-full mx-auto space-y-4">
                {pages.map((page, index) => (
                    <div id={`gallery-page-${page.page}`} key={page.page} className="flex justify-center">
                        <div className="max-w-full">
                            <ScanPage
                                page={page}
                                originalDims={originalDims}
                                shouldFocus={index === targetPageIndex}
                            />
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default ScanGallery;
