
import React, { useEffect, useRef, useState } from 'react';

interface ScanViewerProps {
    imageUrl: string;
    highlightBox: { x: number; y: number; w: number; h: number } | { x: number; y: number; w: number; h: number }[] | null;
    originalDims: { w: number; h: number } | null;
}

const ScanViewer: React.FC<ScanViewerProps> = ({ imageUrl, highlightBox, originalDims }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const imgRef = useRef<HTMLImageElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [loaded, setLoaded] = useState(false);

    // Reset loaded state when image URL changes
    useEffect(() => {
        setLoaded(false);
    }, [imageUrl]);

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
        // We use originalDims as the source of truth for the coordinate system if provided,
        // otherwise fall back to natural dimensions.
        const sourceW = (originalDims ? originalDims.w : img.naturalWidth) || 2500;
        const sourceH = (originalDims ? originalDims.h : img.naturalHeight) || 3800;

        const scaleX = img.clientWidth / sourceW;
        const scaleY = img.clientHeight / sourceH;

        // Pure Scaling based on ratio of displayed size to original source size

        // Normalize to array (handle both single object and array of objects)
        const boxes = Array.isArray(highlightBox) ? highlightBox : [highlightBox];

        // Clear
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        boxes.forEach(box => {
            const x = box.x * scaleX;
            const y = box.y * scaleY;
            const w = box.w * scaleX;
            const h = box.h * scaleY;

            // Semi-transparent yellow fill
            ctx.fillStyle = 'rgba(255, 255, 0, 0.3)';
            ctx.fillRect(x, y, w, h);

            // Solid border
            ctx.strokeStyle = '#F59E0B'; // Amber-500
            ctx.lineWidth = 2;
            ctx.strokeRect(x, y, w, h);
        });



        // Auto-scroll to center the highlight (focus on first box)
        if (containerRef.current && boxes.length > 0) {
            const firstBox = boxes[0];
            const x = firstBox.x * scaleX;
            const y = firstBox.y * scaleY;
            const h = firstBox.h * scaleY;

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
                    className={`absolute top-0 left-0 pointer-events-none z-10 transition-opacity duration-300 ${loaded ? 'opacity-100' : 'opacity-0'}`}
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
