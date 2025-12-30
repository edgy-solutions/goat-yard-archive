import React from 'react';
// Import Footer if we want it embedded, or it can be in App.tsx layout.
// User requested "Micro version" in footer, and this is the Page.
// I will keep it clean.

interface PageProps {
    onClose: () => void;
}

const About: React.FC<PageProps> = ({ onClose }) => {
    return (
        <div className="min-h-full bg-[#FDFBF7] text-[#3E2723] font-serif">
            {/* Custom Header for Overlay */}
            <div className="sticky top-0 z-50 bg-[#FDFBF7] border-b border-[#D7CCC8] px-6 py-4 flex justify-between items-center shadow-sm">
                <h1 className="text-xl font-bold text-[#3E2723]">About Dr. Voluminous</h1>
                <button onClick={onClose} className="text-[#8D6E63] hover:text-[#3E2723] text-sm font-bold px-3 py-1 bg-[#EFEBE9] rounded hover:bg-[#D7CCC8] transition-colors">
                    Close
                </button>
            </div>

            <div className="p-8">

                {/* Pre-Alpha Alert Banner */}
                <div className="bg-amber-50 border-l-4 border-amber-500 p-4 mb-10 rounded-r shadow-sm">
                    <div className="flex">
                        <div className="ml-3">
                            <h3 className="text-sm font-bold text-amber-900 uppercase tracking-wide">
                                Project Status: Pre-Alpha (Work in Progress)
                            </h3>
                            <div className="mt-2 text-sm text-amber-800">
                                <p>
                                    Please note that this application is currently in early development.
                                    The AI may occasionally hallucinate citations or misinterpret complex arguments.
                                    <strong> Always verify citations against the provided scanned images.</strong>
                                </p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Main Content */}
                <div className="prose prose-brown prose-lg max-w-none text-[#3E2723]">

                    <section className="mb-10">
                        <h2 className="text-2xl font-bold text-[#3E2723] mb-4 border-b border-[#D7CCC8] pb-2">The Project</h2>
                        <p>
                            Dr. Voluminous is an AI-powered research assistant dedicated to the theological works of
                            <strong> John Gill (1697–1771)</strong>. Our mission is to make the massive
                            <em> Body of Divinity</em> and his 9-volume <em>Exposition of the Bible</em> accessible,
                            searchable, and interactive for a new generation of pastors, students, and theologians.
                        </p>
                        <p className="italic font-medium text-[#5D4037] border-l-4 border-[#D7CCC8] pl-4 my-4 bg-[#FFFDF5] p-2">
                            It is our intent, D.V., to expand this digital archive to include other
                            significant Particular Baptist works as time and resources permit.
                        </p>
                    </section>

                    <section className="mb-10">
                        <h2 className="text-2xl font-bold text-[#3E2723] mb-4 border-b border-[#D7CCC8] pb-2">The Theologian</h2>
                        <p>
                            John Gill was a prominent 18th-century Particular Baptist pastor and theologian.
                            He pastored the Carter Lane Baptist Church in London (later to become the Metropolitan
                            Tabernacle under C.H. Spurgeon) for over 50 years. His writings are renowned for their
                            profound grasp of the original Hebrew and Greek, their Rabbinic insights, and their
                            unwavering defense of the Doctrines of Grace.
                        </p>
                    </section>

                    <section className="mb-10">
                        <h2 className="text-2xl font-bold text-[#3E2723] mb-4 border-b border-[#D7CCC8] pb-2">Source Material & Attribution</h2>
                        <p>
                            The text data for this application is sourced from the authoritative editions published by
                            <strong> The Baptist Standard Bearer</strong>. We are indebted to their work in
                            preserving and republishing these Baptist classics.
                        </p>
                        <a
                            href="https://standardbearer.org/"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-block bg-[#3E2723] text-[#FFD700] px-6 py-3 rounded hover:bg-[#2D1B18] transition no-underline shadow-md border border-[#2D1B18] font-bold"
                        >
                            Visit The Baptist Standard Bearer Store &rarr;
                        </a>
                    </section>

                </div>
            </div>
        </div>
    );
};

export default About;
