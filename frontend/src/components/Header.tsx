import { SignedIn, SignedOut, SignInButton, UserButton } from "@clerk/clerk-react";

interface HeaderProps {
    onOpenAbout: () => void;
    onOpenContact: () => void;
}

export default function Header({ onOpenAbout, onOpenContact }: HeaderProps) {
    return (
        <div className="p-4 lg:p-6 border-b border-[#D7CCC8] bg-[#FDFBF7]/90 backdrop-blur-md flex justify-between items-center sticky top-0 z-50 shadow-[0_4px_12px_-4px_rgba(44,36,27,0.1)] transition-all">
            <div className="flex flex-col items-start gap-0.5">
                <h1 className="font-serif text-2xl font-bold text-[#4A3B32] tracking-tight leading-none">
                    Dr. Voluminous
                </h1>
                <span className="font-sans text-[0.65rem] font-bold uppercase tracking-[0.2em] text-[#B45309]">
                    Grounded Theological AI
                </span>
            </div>

            <div className="flex items-center space-x-6">
                <nav className="flex space-x-4 text-xs font-bold font-sans uppercase tracking-wider text-[#8D6E63]">
                    <button onClick={onOpenAbout} className="hover:text-[#4A3B32] transition-colors">About</button>
                    <button onClick={onOpenContact} className="hover:text-[#4A3B32] transition-colors">Contact</button>
                    {/* Future: Donate/Store Link */}
                </nav>

                <div className="h-4 w-px bg-[#E5E0D8]"></div>

                <div>
                    <SignedOut>
                        <SignInButton mode="modal">
                            <button className="bg-[#4A3B32] text-[#E6D5B8] px-4 py-1.5 rounded-full text-xs font-bold hover:bg-[#2C241B] transition-colors shadow-sm font-sans tracking-wide">
                                Sign In
                            </button>
                        </SignInButton>
                    </SignedOut>
                    <SignedIn>
                        <UserButton
                            appearance={{
                                elements: {
                                    avatarBox: "w-8 h-8 ring-2 ring-[#E5E0D8]"
                                }
                            }}
                        />
                    </SignedIn>
                </div>
            </div>
        </div>
    );
}
