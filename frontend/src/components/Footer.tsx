

interface FooterProps {
    onOpenPrivacy?: () => void;
    onOpenTerms?: () => void;
}

const Footer: React.FC<FooterProps> = ({ onOpenPrivacy, onOpenTerms }) => {
    return (
        <footer className="mt-auto">
            <div className="max-w-7xl mx-auto px-6 md:flex md:items-center md:justify-between flex-wrap gap-4">

                {/* Left Side: Copyright */}
                <div className="flex-1 min-w-[200px] flex items-center space-x-4 justify-center md:justify-start">
                    <p className="text-xs text-[#8D6E63] italic whitespace-nowrap">
                        &copy; {new Date().getFullYear()} Dr. Voluminous (Pre-Alpha v0.1).
                    </p>
                    {onOpenPrivacy && (
                        <button
                            onClick={onOpenPrivacy}
                            className="text-xs text-[#8D6E63] hover:text-[#D7CCC8] underline decoration-dotted transition-colors whitespace-nowrap"
                        >
                            Privacy Policy
                        </button>
                    )}
                    {onOpenTerms && (
                        <button
                            onClick={onOpenTerms}
                            className="text-xs text-[#8D6E63] hover:text-[#D7CCC8] underline decoration-dotted transition-colors whitespace-nowrap"
                        >
                            Terms of Use
                        </button>
                    )}
                </div>

                {/* Right Side: Links */}
                <div className="flex-1 min-w-[200px] flex justify-center md:justify-end items-center space-x-4 md:space-x-6 flex-wrap">
                    <span className="text-[#D7CCC8] text-xs whitespace-nowrap">Powered by <a href="https://www.edgy-solutions.com" className="hover:text-amber-400 text-amber-200/80 transition-colors underline decoration-amber-800/50">Edgy Solutions</a></span>
                    <span className="text-[#5D4037] text-xs hidden md:inline">|</span>
                    <span className="text-[#D7CCC8] text-xs whitespace-nowrap">Text via <a href="https://standardbearer.org/" className="hover:text-amber-400 text-amber-200/80 transition-colors underline decoration-amber-800/50">Baptist Standard Bearer</a></span>
                </div>

            </div>
        </footer>
    );
};

export default Footer;
