import { SignedIn, SignedOut, SignInButton, UserButton } from "@clerk/clerk-react";

export default function Header() {
    return (
        <div className="p-4 border-b border-[#5D4037] bg-wood text-gold shadow-md flex justify-between items-center">
            <div>
                <h1 className="text-2xl font-bold tracking-wide">Dr. Voluminous</h1>
                <p className="text-xs text-amber-200/80 italic">Grounded Theological AI</p>
            </div>
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
    );
}
