import { SignedIn, SignedOut, SignInButton, UserButton } from "@clerk/clerk-react";

interface HeaderProps {
    onOpenAbout: () => void;
    onOpenContact: () => void;
}

export default function Header({ onOpenAbout, onOpenContact }: HeaderProps) {
    return (
        <div className="p-4 border-b border-[#5D4037] bg-wood text-gold shadow-md flex justify-between items-center">
            <div>
                <h1 className="text-2xl font-bold tracking-wide">Dr. Voluminous</h1>
                <p className="text-xs text-amber-200/80 italic">Grounded Theological AI</p>
            </div>

            <div className="flex items-center space-x-6">
                <nav className="flex space-x-4 text-sm font-medium">
                    <button onClick={onOpenAbout} className="hover:text-amber-200 transition-colors">About</button>
                    <button onClick={onOpenContact} className="hover:text-amber-200 transition-colors">Contact</button>
                    {/* Future: Donate/Store Link */}
                </nav>

                <div className="h-6 w-px bg-amber-800/50"></div>

                <div>
                    <SignedOut>
                        <SignInButton mode="modal">
                            <button className="bg-amber-100 text-amber-900 px-3 py-1 rounded text-sm font-bold hover:bg-amber-200 transition-colors border border-amber-300">
                                Sign In
                            </button>
                        </SignInButton>
                    </SignedOut>
                    <SignedIn>
                        <UserButton
                            appearance={{
                                elements: {
                                    avatarBox: "w-8 h-8 ring-2 ring-amber-500"
                                }
                            }}
                        />
                    </SignedIn>
                </div>
            </div>
        </div>
    );
}
