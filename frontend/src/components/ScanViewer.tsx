
import React, { useEffect, useRef, useState } from 'react';

interface ScanViewerProps {
    imageUrl: string;
    highlightBox: { x: number; y: number; w: number; h: number } | null;
    originalDims: { w: number; h: number } | null;
}

const ScanViewer: React.FC<ScanViewerProps> = ({ imageUrl, highlightBox, originalDims }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const imgRef = useRef<HTMLImageElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [loaded, setLoaded] = useState(false);

    // Draw Highlight when image loads or box changes
    useEffect(() => {
        if (!loaded || !imgRef.current || !canvasRef.current || !highlightBox) return;

        const img = imgRef.current;
        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d');

        if (!ctx) return;

        // Match canvas size to rendered image size
        canvas.width = img.clientWidth;
        canvas.height = img.clientHeight;

        // Calculate Scale
        // We use natural dimensions of the image as the source of truth for the coordinate system
        // This assumes the OCR was run on the exact same image resolution as what we are displaying.
        const sourceW = img.naturalWidth || (originalDims ? originalDims.w : 2500);
        const sourceH = img.naturalHeight || (originalDims ? originalDims.h : 3800);

        const scaleX = img.clientWidth / sourceW;
        const scaleY = img.clientHeight / sourceH;

        // Manual Offset Correction (based on user feedback)
        // Tune 12: +2px Down (Screen) -> +4 Y source.
        // Tune 12: +2px Down (Screen) -> +4 Y source. Final: 195/109.
        const OFFSET_X = 195;
        const OFFSET_Y = 109;

        // Tune 17: Another +5px (screen). Total +65 screen -> +130 source.
        const PADDING_H = 130;
        // Tune 19: Another +5px (screen). Total +10 screen -> +20 source.
        const PADDING_W = 20;

        const x = (highlightBox.x + OFFSET_X) * scaleX;
        const y = (highlightBox.y + OFFSET_Y) * scaleY;
        const w = (highlightBox.w + PADDING_W) * scaleX;
        const h = (highlightBox.h + PADDING_H) * scaleY;

        // Clear & Draw
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Semi-transparent yellow fill
        ctx.fillStyle = 'rgba(255, 255, 0, 0.3)';
        ctx.fillRect(x, y, w, h);

        // Solid border
        ctx.strokeStyle = '#F59E0B'; // Amber-500
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);

        // Auto-scroll to center the highlight
        if (containerRef.current) {
            const containerBy = containerRef.current.clientHeight;
            // Center of box
            const centerY = y + (h / 2);
            // Don't scroll if we are already seeing it or standard behavior 
            // Minimal scroll or center? Centering is nice.
            containerRef.current.scrollTo({
                top: centerY - (containerBy / 2),
                behavior: 'smooth'
            });
        }

    }, [imageUrl, highlightBox, originalDims, loaded]);

    return (
        <div className="relative w-full h-full overflow-auto bg-gray-100" ref={containerRef}>
            <div className="relative w-full min-h-screen">
                {/* Image */}
                <img
                    ref={imgRef}
                    src={imageUrl}
                    alt="Scanned Page"
                    className="w-full h-auto block"
                    onLoad={() => setLoaded(true)}
                />

                {/* Canvas Overlay */}
                <canvas
                    ref={canvasRef}
                    className="absolute top-0 left-0 pointer-events-none z-10 border border-red-500"
                />

                {/* Placeholder if no image */}
                {!imageUrl && (
                    <div className="flex items-center justify-center p-10 text-gray-500">
                        No Scan Loaded
                    </div>
                )}
            </div>
        </div>
    );
};

export default ScanViewer;
