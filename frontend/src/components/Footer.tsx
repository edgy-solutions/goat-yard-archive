

interface FooterProps {
    onOpenPrivacy?: () => void;
    onOpenTerms?: () => void;
}

const Footer: React.FC<FooterProps> = ({ onOpenPrivacy, onOpenTerms }) => {
    return (
        <footer className="bg-[#2D1B18] border-t border-[#5D4037] mt-auto">
            <div className="max-w-7xl mx-auto py-2 px-4 sm:px-6 md:flex md:items-center md:justify-between">

                {/* Left Side: Copyright */}
                <div className="mt-4 md:mt-0 md:order-1 flex items-center space-x-4">
                    <p className="text-center text-xs text-[#8D6E63] italic">
                        &copy; {new Date().getFullYear()} Dr. Voluminous (Pre-Alpha v0.1).
                    </p>
                    {onOpenPrivacy && (
                        <button
                            onClick={onOpenPrivacy}
                            className="text-xs text-[#8D6E63] hover:text-[#D7CCC8] underline decoration-dotted transition-colors"
                        >
                            Privacy Policy
                        </button>
                    )}
                    {onOpenTerms && (
                        <button
                            onClick={onOpenTerms}
                            className="text-xs text-[#8D6E63] hover:text-[#D7CCC8] underline decoration-dotted transition-colors"
                        >
                            Terms of Use
                        </button>
                    )}
                </div>

                {/* Right Side: Links */}
                <div className="flex justify-center items-center space-x-6 md:order-2">
                    <span className="text-[#D7CCC8] text-xs">Powered by <a href="https://www.edgy-solutions.com" className="hover:text-amber-400 text-amber-200/80 transition-colors underline decoration-amber-800/50">Edgy Solutions</a></span>
                    <span className="text-[#5D4037] text-xs">|</span>
                    <span className="text-[#D7CCC8] text-xs">Text via <a href="https://standardbearer.org/" className="hover:text-amber-400 text-amber-200/80 transition-colors underline decoration-amber-800/50">Baptist Standard Bearer</a></span>
                </div>

            </div>
        </footer>
    );
};

export default Footer;
