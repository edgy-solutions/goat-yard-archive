

interface FooterProps {
    onOpenPrivacy?: () => void;
    onOpenTerms?: () => void;
    variant?: 'main' | 'gallery' | 'full'; // Main = copyright/privacy/terms, Gallery = powered by/text via, Full = all
}

const Footer: React.FC<FooterProps> = ({ onOpenPrivacy, onOpenTerms, variant = 'full' }) => {
    if (variant === 'main') {
        // Main screen footer (mobile only): Copyright, Privacy, Terms
        return (
            <footer className="mt-auto w-full">
                <div className="px-4 py-2 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs">
                    <span className="text-[#8D6E63] italic">
                        © {new Date().getFullYear()} Dr. Voluminous
                    </span>
                    {onOpenPrivacy && (
                        <button
                            onClick={onOpenPrivacy}
                            className="text-[#8D6E63] hover:text-[#5D4037] underline decoration-dotted transition-colors"
                        >
                            Privacy
                        </button>
                    )}
                    {onOpenTerms && (
                        <button
                            onClick={onOpenTerms}
                            className="text-[#8D6E63] hover:text-[#5D4037] underline decoration-dotted transition-colors"
                        >
                            Terms
                        </button>
                    )}
                </div>
            </footer>
        );
    }

    if (variant === 'gallery') {
        // Gallery-only footer (mobile gallery): Powered by, Text via
        return (
            <footer className="mt-auto w-full">
                <div className="px-6 py-2 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs">
                    <span className="text-[#D7CCC8] text-center">
                        Powered by <a href="https://www.edgy-solutions.com" className="text-[#E6D5AC] hover:text-white transition-colors underline decoration-[#B45309]/50">Edgy Solutions</a>
                    </span>
                    <span className="text-[#5D4037]">|</span>
                    <span className="text-[#D7CCC8] text-center">
                        Text via <a href="https://standardbearer.org/" className="text-[#E6D5AC] hover:text-white transition-colors underline decoration-[#B45309]/50">Baptist Standard Bearer</a>
                    </span>
                </div>
            </footer>
        );
    }

    // Full footer (desktop): All content
    return (
        <footer className="mt-auto w-full">
            <div className="px-6 py-2 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs">
                <span className="text-[#8D6E63] italic">
                    © {new Date().getFullYear()} Dr. Voluminous
                </span>
                {onOpenPrivacy && (
                    <button
                        onClick={onOpenPrivacy}
                        className="text-[#8D6E63] hover:text-[#D7CCC8] underline decoration-dotted transition-colors"
                    >
                        Privacy
                    </button>
                )}
                {onOpenTerms && (
                    <button
                        onClick={onOpenTerms}
                        className="text-[#8D6E63] hover:text-[#D7CCC8] underline decoration-dotted transition-colors"
                    >
                        Terms
                    </button>
                )}
                <span className="text-[#5D4037]">|</span>
                <span className="text-[#D7CCC8] text-center">
                    Powered by <a href="https://www.edgy-solutions.com" className="text-[#E6D5AC] hover:text-white transition-colors underline decoration-[#B45309]/50">Edgy Solutions</a>
                </span>
                <span className="text-[#5D4037]">|</span>
                <span className="text-[#D7CCC8] text-center">
                    Text via <a href="https://standardbearer.org/" className="text-[#E6D5AC] hover:text-white transition-colors underline decoration-[#B45309]/50">Baptist Standard Bearer</a>
                </span>
            </div>
        </footer>
    );
};

export default Footer;

