

interface FooterProps {
    onOpenPrivacy?: () => void;
    onOpenTerms?: () => void;
}

const Footer: React.FC<FooterProps> = ({ onOpenPrivacy, onOpenTerms }) => {
    return (
        <footer className="mt-auto w-full">
            {/* Compact single row - removed max-w constraint to fit in narrow panes */}
            <div className="px-6 flex items-center justify-between gap-4 text-xs">

                {/* Left Side: Copyright */}
                <div className="flex items-center gap-4 shrink min-w-0">
                    <span className="text-[#8D6E63] italic whitespace-nowrap">
                        © {new Date().getFullYear()} Dr. Voluminous (Pre-Alpha v0.1).
                    </span>
                    {onOpenPrivacy && (
                        <button
                            onClick={onOpenPrivacy}
                            className="text-[#8D6E63] hover:text-[#D7CCC8] underline decoration-dotted transition-colors whitespace-nowrap hidden md:inline"
                        >
                            Privacy Policy
                        </button>
                    )}
                    {onOpenTerms && (
                        <button
                            onClick={onOpenTerms}
                            className="text-[#8D6E63] hover:text-[#D7CCC8] underline decoration-dotted transition-colors whitespace-nowrap hidden md:inline"
                        >
                            Terms of Use
                        </button>
                    )}
                </div>

                {/* Right Side: Links */}
                <div className="flex items-center gap-4 shrink-0">
                    <span className="text-[#D7CCC8] whitespace-nowrap">
                        Powered by <a href="https://www.edgy-solutions.com" className="text-[#E6D5AC] hover:text-white transition-colors underline decoration-[#B45309]/50">Edgy Solutions</a>
                    </span>
                    <span className="text-[#5D4037] hidden lg:inline">|</span>
                    <span className="text-[#D7CCC8] whitespace-nowrap hidden lg:inline">
                        Text via <a href="https://standardbearer.org/" className="text-[#E6D5AC] hover:text-white transition-colors underline decoration-[#B45309]/50">Baptist Standard Bearer</a>
                    </span>
                </div>

            </div>
        </footer>
    );
};

export default Footer;
