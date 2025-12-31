import React, { useState } from 'react';

interface ReportModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (issueType: string, description: string) => void;
}

const ISSUE_TYPES = [
    { id: 'hallucination', label: 'Hallucination / Incorrect Info' },
    { id: 'bad_citation', label: 'Bad Citation / Wrong Page' },
    { id: 'formatting', label: 'Formatting Issue' },
    { id: 'other', label: 'Other' }
];

const ReportModal: React.FC<ReportModalProps> = ({ isOpen, onClose, onSubmit }) => {
    const [issueType, setIssueType] = useState('hallucination');
    const [description, setDescription] = useState('');

    if (!isOpen) return null;

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSubmit(issueType, description);
        setDescription('');
        setIssueType('hallucination');
        onClose();
    };

    return (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200">
            <div className="bg-[#FFFDF5] w-full max-w-md rounded-lg shadow-2xl border border-[#8D6E63] overflow-hidden animate-in zoom-in-95 duration-200">
                <div className="bg-[#EFEBE9] px-6 py-4 border-b border-[#D7CCC8] flex justify-between items-center">
                    <h3 className="text-[#3E2723] font-bold uppercase tracking-wide">Report Issue</h3>
                    <button onClick={onClose} className="text-[#8D6E63] hover:text-[#3E2723] transition-colors">✕</button>
                </div>

                <form onSubmit={handleSubmit} className="p-6 space-y-4">
                    <div>
                        <label className="block text-xs font-bold uppercase text-[#5D4037] mb-2 tracking-wider">What's wrong?</label>
                        <div className="grid grid-cols-1 gap-2">
                            {ISSUE_TYPES.map(type => (
                                <label key={type.id} className={`
                                    flex items-center p-3 rounded border cursor-pointer transition-all
                                    ${issueType === type.id
                                        ? 'bg-[#5D4037] text-white border-[#3E2723] shadow-md'
                                        : 'bg-white text-[#5D4037] border-[#D7CCC8] hover:bg-[#D7CCC8]/20'
                                    }
                                `}>
                                    <input
                                        type="radio"
                                        name="issueType"
                                        value={type.id}
                                        checked={issueType === type.id}
                                        onChange={(e) => setIssueType(e.target.value)}
                                        className="hidden"
                                    />
                                    <span className="text-sm font-serif">{type.label}</span>
                                </label>
                            ))}
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs font-bold uppercase text-[#5D4037] mb-2 tracking-wider">Details (Optional)</label>
                        <textarea
                            className="w-full p-3 border border-[#BCAAA4] rounded bg-white text-[#3E2723] placeholder-[#A1887F] focus:outline-none focus:ring-2 focus:ring-[#8D6E63] focus:border-transparent font-serif shadow-inner resize-none h-24 text-sm"
                            placeholder="Tell us more about what happened..."
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                        />
                    </div>

                    <div className="flex justify-end gap-3 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 rounded text-[#5D4037] hover:bg-[#D7CCC8]/30 font-serif text-sm"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            className="bg-wood text-gold px-6 py-2 rounded font-bold uppercase tracking-wide hover:bg-[#2D1B18] transition-colors shadow-md border border-[#2D1B18] text-sm"
                        >
                            Submit Report
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default ReportModal;
