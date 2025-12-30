import React from 'react';

interface PageProps {
    onClose: () => void;
}

const Contact: React.FC<PageProps> = ({ onClose }) => {
    return (
        <div className="min-h-full bg-[#FDFBF7] text-[#3E2723] font-serif">
            {/* Custom Header for Overlay */}
            <div className="sticky top-0 z-50 bg-[#FDFBF7] border-b border-[#D7CCC8] px-6 py-4 flex justify-between items-center shadow-sm">
                <h1 className="text-xl font-bold text-[#3E2723]">Contact & Support</h1>
                <button onClick={onClose} className="text-[#8D6E63] hover:text-[#3E2723] text-sm font-bold px-3 py-1 bg-[#EFEBE9] rounded hover:bg-[#D7CCC8] transition-colors">
                    Close
                </button>
            </div>

            <div className="p-8">

                {/* Main Content */}
                <div className="prose prose-brown prose-lg max-w-none text-[#3E2723]">

                    <section className="mb-10">
                        <h2 className="text-2xl font-bold text-[#3E2723] mb-4 border-b border-[#D7CCC8] pb-2">Developer Support</h2>
                        <p>
                            This project is developed and maintained by <strong>Edgy Solutions</strong>.
                            We specialize in building robust software solutions for complex data problems.
                        </p>
                        <ul className="list-none pl-0">
                            <li className="mb-2">
                                <strong>Email: </strong>
                                <a href="mailto:support@goatyardarchive.org" className="text-amber-800 hover:text-amber-600 hover:underline">support@goatyardarchive.org</a>
                            </li>
                            <li className="mb-2">
                                <strong>Web: </strong>
                                <a href="https://www.edgy-solutions.com" target="_blank" rel="noopener noreferrer" className="text-amber-800 hover:text-amber-600 hover:underline">www.edgy-solutions.com</a>
                            </li>
                        </ul>
                    </section>

                    <section className="mb-10">
                        <h2 className="text-2xl font-bold text-[#3E2723] mb-4 border-b border-[#D7CCC8] pb-2">Ecclesiastical Affiliation</h2>
                        <p>
                            The developer is a member of <strong>Rogersville Baptist Church</strong>,
                            a Particular Baptist congregation in North Alabama. We confess the
                            <em> 1689 London Baptist Confession of Faith</em> and seek to honor Christ in both our worship and our code.
                        </p>
                        <ul className="list-none pl-0">
                            <li className="mb-2">
                                <strong>Church Website: </strong>
                                <a href="https://www.rogersvillebaptistchurch.org/" target="_blank" rel="noopener noreferrer" className="text-amber-800 hover:text-amber-600 hover:underline">rogersvillebaptistchurch.org</a>
                            </li>
                        </ul>
                    </section>

                    <section className="mb-10 bg-[#FFFDF5] p-6 rounded-lg border border-[#D7CCC8] shadow-sm">
                        <h2 className="text-xl font-bold text-[#3E2723] mb-2 mt-0">Report an Issue</h2>
                        <p className="mb-4 text-sm text-[#5D4037]">
                            Encountered a bug, a hallucination, or a missing page? We appreciate your feedback.
                        </p>
                        <a
                            href="mailto:support@goatyardarchive.org?subject=Dr. Voluminous Bug Report"
                            className="inline-block bg-white border border-[#BCAAA4] text-[#3E2723] px-4 py-2 rounded hover:bg-[#FDFBF7] transition no-underline text-sm font-bold shadow-sm"
                        >
                            Submit Feedback
                        </a>
                    </section>

                </div>
            </div>
        </div>
    );
};

export default Contact;
