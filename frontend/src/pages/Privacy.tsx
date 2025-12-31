import React from 'react';

interface PrivacyProps {
    onClose: () => void;
    onOpenContact?: () => void;
}

const Privacy: React.FC<PrivacyProps> = ({ onClose, onOpenContact }) => {
    return (
        <div className="relative bg-[#FFFDF5] min-h-full">
            {/* Sticky Header */}
            <div className="sticky top-0 z-10 bg-[#EFEBE9] px-6 py-4 border-b border-[#D7CCC8] flex justify-between items-center shadow-sm">
                <h1 className="text-[#3E2723] font-serif font-bold text-xl uppercase tracking-wide">Privacy Policy</h1>
                <button
                    onClick={onClose}
                    className="text-[#8D6E63] hover:text-[#3E2723] flex items-center gap-2 font-bold px-3 py-1 rounded hover:bg-[#D7CCC8]/30 transition-colors"
                    title="Close"
                >
                    <span className="text-lg">✕</span>
                    <span className="text-sm uppercase tracking-wider">Close</span>
                </button>
            </div>

            <div className="max-w-4xl mx-auto px-6 py-12">

                {/* Date Header */}
                <div className="border-b border-[#D7CCC8] pb-6 mb-8">
                    <p className="text-[#8D6E63] font-serif italic">Last updated: December 31, 2025</p>
                </div>

                {/* Main Content */}
                <div className="prose prose-stone max-w-none text-[#5D4037] space-y-8 font-serif leading-relaxed">

                    <p>
                        This Privacy Notice for <strong>Edgy Solutions</strong> ("we," "us," or "our"),
                        describes how and why we might access, collect, store, use, and/or share ("process")
                        your personal information when you use our services ("Services"), including when you visit our website
                        at <strong>https://goatyardarchive.org</strong> or use the Dr. Voluminous application.
                    </p>

                    <section>
                        <h2 className="text-xl font-bold text-[#3E2723] mb-3 uppercase tracking-wider">1. WHAT INFORMATION DO WE COLLECT?</h2>
                        <p className="mb-2"><strong>Personal information you disclose to us</strong></p>
                        <p className="mb-4">We collect personal information that you voluntarily provide to us when you register on the Services, express an interest in obtaining information about us or our products and Services, or otherwise when you contact us.</p>
                        <ul className="list-disc pl-5 space-y-1 marker:text-[#8D6E63]">
                            <li>Usernames</li>
                            <li>Email addresses (Authentication Data)</li>
                            <li>Usage Data (Search queries, reading history)</li>
                        </ul>
                    </section>

                    {/* --- CUSTOM CLAUSE (CORRECTED & STYLED) --- */}
                    <div className="bg-[#EFEBE9] border-l-4 border-[#8D6E63] p-6 my-6 rounded-r shadow-inner">
                        <h2 className="text-xl font-bold text-[#3E2723] mb-3 uppercase tracking-wider">2. THIRD-PARTY DATA PROCESSORS (The Tech Stack)</h2>
                        <p className="mb-4">We use trusted third-party services to operate and improve our application. By using the Service, you acknowledge the use of:</p>
                        <ul className="list-disc pl-5 space-y-4 marker:text-[#8D6E63]">
                            <li>
                                <strong>Identity & Authentication:</strong> We use Clerk to manage secure log-ins. Your email and identity data are processed by Clerk in accordance with their Privacy Policy.
                            </li>
                            <li>
                                <strong>Visual Analytics:</strong> We use PostHog to analyze user behavior (clicks, navigation). This includes <strong>Session Replay</strong>, which creates a visual reconstruction of your interaction.
                                <em className="block mt-1 text-[#8D6E63] border-l-2 border-[#D7CCC8] pl-2"> Note: To protect your privacy, we mask input fields in these video replays. We do not "watch" you type in real-time.</em>
                            </li>
                            <li>
                                <strong>AI Processing & Logging:</strong>
                                Unlike the visual replays above, <strong>your actual search queries and chat inputs ARE logged</strong> in our secure backend systems (Langfuse) and sent to our AI providers.
                                <br />
                                <span className="block mt-2 font-bold text-[#5D4037]">Why? This data is strictly necessary to:</span>
                                <ul className="list-disc pl-5 mt-1 text-sm text-[#5D4037]/80">
                                    <li>Generate the answers you requested.</li>
                                    <li>Debug errors (e.g., if the AI hallucinates a citation, we need to see the query to fix it).</li>
                                    <li>Improve the accuracy of the theological engine.</li>
                                </ul>
                            </li>
                        </ul>
                    </div>
                    {/* ----------------------------------- */}

                    <section>
                        <h2 className="text-xl font-bold text-[#3E2723] mb-3 uppercase tracking-wider">3. HOW DO WE PROCESS YOUR INFORMATION?</h2>
                        <p>We process your information to provide, improve, and administer our Services, communicate with you, for security and fraud prevention, and to comply with law. We may also process your information for other purposes with your consent.</p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-[#3E2723] mb-3 uppercase tracking-wider">4. WHEN AND WITH WHOM DO WE SHARE YOUR PERSONAL INFORMATION?</h2>
                        <p>We may share information in specific situations and with specific categories of third parties, primarily:</p>
                        <ul className="list-disc pl-5 space-y-1 marker:text-[#8D6E63]">
                            <li>AI Platforms (for generating content)</li>
                            <li>Performance Monitoring Tools (for debugging)</li>
                            <li>User Account Registration & Authentication Services (Clerk)</li>
                        </ul>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-[#3E2723] mb-3 uppercase tracking-wider">5. DO WE USE COOKIES AND OTHER TRACKING TECHNOLOGIES?</h2>
                        <p>We may use cookies and similar tracking technologies (like web beacons and pixels) to gather information when you interact with our Services. We use a "Strict Opt-In" policy for analytics cookies, meaning we do not track your session until you explicitly consent.</p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-[#3E2723] mb-3 uppercase tracking-wider">6. ARTIFICIAL INTELLIGENCE PRODUCTS</h2>
                        <p>We offer products, features, or tools powered by artificial intelligence (AI). All personal information processed using our AI Products is handled in line with this Privacy Notice. You acknowledge that AI outputs are generated probabilistically and may contain inaccuracies.</p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-[#3E2723] mb-3 uppercase tracking-wider">7. HOW DO WE HANDLE YOUR SOCIAL LOGINS?</h2>
                        <p>If you choose to register or log in to our Services using a social media account, we may have access to certain information about you. We will use the information we receive only for the purposes that are described in this Privacy Notice.</p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-[#3E2723] mb-3 uppercase tracking-wider">8. HOW LONG DO WE KEEP YOUR INFORMATION?</h2>
                        <p>We keep your information for as long as necessary to fulfill the purposes outlined in this Privacy Notice unless otherwise required by law. We retain account data for the duration of your account's existence. You may request deletion at any time.</p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-[#3E2723] mb-3 uppercase tracking-wider">9. HOW DO WE KEEP YOUR INFORMATION SAFE?</h2>
                        <p>We have implemented appropriate and reasonable technical and organizational security measures designed to protect the security of any personal information we process. However, no electronic transmission over the Internet can be guaranteed to be 100% secure.</p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-[#3E2723] mb-3 uppercase tracking-wider">10. DO WE COLLECT INFORMATION FROM MINORS?</h2>
                        <p>We do not knowingly collect data from or market to children under 18 years of age. By using the Services, you represent that you are at least 18.</p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-[#3E2723] mb-3 uppercase tracking-wider">11. YOUR PRIVACY RIGHTS</h2>
                        <p>Depending on your location (e.g., EEA, UK, Canada, various US states), you may have the right to request access to, correction of, or deletion of your personal information. To exercise these rights, please contact us.</p>
                    </section>

                    <section className="border-t border-[#D7CCC8] pt-8 mt-8">
                        <h2 className="text-xl font-bold text-[#3E2723] mb-3 uppercase tracking-wider">12. CONTACT US</h2>
                        <p className="mb-4">If you have questions or comments about this notice, you may contact us at:</p>
                        <div className="bg-[#EFEBE9] p-6 rounded text-[#5D4037] border border-[#D7CCC8]">
                            <p className="font-bold text-[#3E2723]">Edgy Solutions</p>
                            <p>Rogersville, AL 35652</p>
                            <p>United States</p>
                            <p className="mt-4"><strong>Email:</strong> privacy@goatyardarchive.org</p>
                            <p><strong>Support:</strong> <button onClick={onOpenContact} className="text-amber-800 underline hover:text-[#3E2723] bg-transparent border-0 p-0 cursor-pointer">Contact Form</button></p>
                        </div>
                    </section>

                </div>
            </div>
        </div>
    );
};

export default Privacy;