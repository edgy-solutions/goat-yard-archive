import React, { useState, useEffect } from 'react';

export interface MatrixData {
  chunk_id: string;
  citation: string;
  book: string;
  entities: string[];
  verse_ref?: string;
  volume?: number;
  page_number?: number;
}

export interface MatrixResponse {
  search_term: string;
  total_hits: number;
  matrix_data: MatrixData[];
}

interface TopicMatrixSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  query: string;
  onCitationClick: (chunkId: string) => void;
  getToken?: () => Promise<string | null>;
}

export const TopicMatrixSidebar: React.FC<TopicMatrixSidebarProps> = ({ isOpen, onClose, query, onCitationClick, getToken }) => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<MatrixResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [grouping, setGrouping] = useState<'book' | 'topic'>('topic');
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});
  const [summaries, setSummaries] = useState<Record<string, { text: string, loading: boolean, cached: boolean }>>({});

  useEffect(() => {
    if (isOpen && query) {
      fetchMatrixData();
    }
  }, [isOpen, query]);

  const fetchMatrixData = async () => {
    setLoading(true);
    setError(null);
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (getToken) {
        const token = await getToken();
        if (token) {
          headers['Authorization'] = `Bearer ${token}`;
        }
      }
      const response = await fetch('/api/search/matrix', {
        method: 'POST',
        headers,
        body: JSON.stringify({ query, limit: 500 }),
      });
      if (!response.ok) throw new Error('Failed to fetch matrix data');
      const result = await response.json();
      setData(result);
      // Initialize all sections as collapsed
      setExpandedSections({});
      // Reset summaries
      setSummaries({});
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateSummary = async (groupKey: string, chunkIds: string[]) => {
    setSummaries(prev => ({ ...prev, [groupKey]: { text: '', loading: true, cached: false } }));
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (getToken) {
        const token = await getToken();
        if (token) {
          headers['Authorization'] = `Bearer ${token}`;
        }
      }
      const response = await fetch('/api/summarize_group', {
        method: 'POST',
        headers,
        body: JSON.stringify({ query, group_name: groupKey, chunk_ids: chunkIds }),
      });
      if (!response.ok) throw new Error('Failed to generate summary');
      const result = await response.json();
      setSummaries(prev => ({
        ...prev,
        [groupKey]: { text: result.summary, loading: false, cached: result.cached }
      }));
    } catch (err: any) {
      setSummaries(prev => ({
        ...prev,
        [groupKey]: { text: `Error: ${err.message}`, loading: false, cached: false }
      }));
    }
  };

  const toggleSection = (key: string) => {
    setExpandedSections(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const getGroupedData = () => {
    if (!data?.matrix_data) return {};

    const grouped: Record<string, MatrixData[]> = {};

    data.matrix_data.forEach(item => {
      let key = 'Uncategorized';
      if (grouping === 'book') {
        key = item.book || 'Unknown Book';
      } else if (grouping === 'topic') {
        key = (item.entities && item.entities.length > 0) ? item.entities[0] : 'Uncategorized';
      }

      if (!grouped[key]) {
        grouped[key] = [];
      }
      grouped[key].push(item);
    });

    return grouped;
  };

  const groupedData = getGroupedData();
  const sortedKeys = Object.keys(groupedData).sort((a, b) => {
    if (a === 'Uncategorized') return 1;
    if (b === 'Uncategorized') return -1;
    return groupedData[b].length - groupedData[a].length; // Sort by count descending
  });

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && <div className="fixed inset-0 bg-black/20 z-[90] md:hidden" onClick={onClose} />}

      {/* Desktop: inline flex panel that grows/shrinks; Mobile: fixed bottom sheet */}
      <div className={`z-[100] bg-white shadow-2xl flex flex-col transition-all duration-300 ease-in-out overflow-hidden
        md:static md:h-full md:border-r md:border-[#E5E0D8] md:shadow-none
        ${isOpen ? 'md:w-96 md:opacity-100' : 'md:w-0 md:opacity-0'}
        fixed inset-x-0 bottom-0 h-[75vh] rounded-t-2xl border-t border-[#E5E0D8]
        ${isOpen ? 'translate-y-0' : 'translate-y-full'}
        md:translate-y-0 md:rounded-none md:border-t-0
      `}>
        {/* Header */}
      <div className="p-4 border-b border-[#E5E0D8] bg-[#FAF9F5] flex justify-between items-center shrink-0">
        <div>
          <h2 className="font-serif font-bold text-[#5D4037] text-lg">Search Matrix</h2>
          <p className="text-xs text-[#8D6E63] font-ui uppercase tracking-wider mt-1">
            {data ? `"${data.search_term}" (${data.total_hits} hits)` : (query ? `"${query}"` : 'No search')}
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-[#8D6E63] hover:text-[#5D4037] p-2 rounded-full hover:bg-[#E5E0D8] transition-colors"
        >
          ✕
        </button>
      </div>

      {/* Controls */}
      <div className="p-4 border-b border-[#E5E0D8] bg-white flex justify-center gap-2">
        <button
          onClick={() => setGrouping('topic')}
          className={`flex-1 py-1.5 px-3 rounded-full text-xs font-ui font-bold uppercase tracking-wider transition-colors ${
            grouping === 'topic' 
              ? 'bg-[#2C241B] text-[#E6D5B8]' 
              : 'bg-[#FDFBF7] text-[#8D6E63] border border-[#E5E0D8] hover:bg-[#FAF9F5]'
          }`}
        >
          By Topic
        </button>
        <button
          onClick={() => setGrouping('book')}
          className={`flex-1 py-1.5 px-3 rounded-full text-xs font-ui font-bold uppercase tracking-wider transition-colors ${
            grouping === 'book' 
              ? 'bg-[#2C241B] text-[#E6D5B8]' 
              : 'bg-[#FDFBF7] text-[#8D6E63] border border-[#E5E0D8] hover:bg-[#FAF9F5]'
          }`}
        >
          By Book
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-4 bg-[#FDFBF7]">
        {loading && (
          <div className="flex items-center justify-center py-10 space-x-2 text-[#8D6E63] animate-pulse">
            <span className="text-xs font-medium uppercase tracking-widest font-ui">Loading Matrix...</span>
          </div>
        )}
        
        {error && (
          <div className="bg-red-50 text-red-800 p-3 rounded-md text-sm font-ui border border-red-200">
            Failed to load matrix: {error}
          </div>
        )}

        {!loading && !error && data && sortedKeys.map(key => (
          <div key={key} className="mb-3 border border-[#E5E0D8] rounded-lg bg-white overflow-hidden shadow-sm">
            <button 
              onClick={() => toggleSection(key)}
              className="w-full flex justify-between items-center p-3 text-left hover:bg-[#FAF9F5] transition-colors"
            >
              <span className="font-serif font-medium text-[#5D4037]">{key} <span className="text-xs text-[#A1887F] font-ui ml-1">({groupedData[key].length})</span></span>
              <span className="text-[#A1887F] text-xs">{expandedSections[key] ? '▼' : '▶'}</span>
            </button>
            
            {expandedSections[key] && (
              <div className="p-3 border-t border-[#E5E0D8] bg-[#FDFBF7]">
                {!summaries[key] ? (
                  <button 
                    onClick={() => handleGenerateSummary(key, groupedData[key].map(item => item.chunk_id))}
                    className="w-full mb-3 py-1.5 text-xs font-ui font-bold uppercase tracking-wider bg-[#EDE0D4] text-[#5D4037] rounded hover:bg-[#D7CCC8] transition-colors"
                  >
                    Generate Summary
                  </button>
                ) : summaries[key].loading ? (
                  <div className="flex items-center justify-center py-4 mb-3 space-x-2 text-[#8D6E63] animate-pulse">
                    <span className="text-xs font-medium uppercase tracking-widest font-ui">Consulting Dr. Gill...</span>
                  </div>
                ) : summaries[key].text ? (
                  <div className="bg-[#EDE0D4]/30 p-3 rounded text-[#3E2723] text-sm font-serif mb-3 relative">
                    {summaries[key].cached && (
                      <span className="absolute -top-2 -right-2 bg-[#E6D5B8] text-[#5D4037] text-[9px] font-ui font-bold uppercase px-2 py-0.5 rounded-full border border-[#D7CCC8] shadow-sm">
                        ⚡ Instantly loaded from cache
                      </span>
                    )}
                    {summaries[key].text}
                  </div>
                ) : null}
                <ul className="space-y-1.5">
                  {groupedData[key].map(item => (
                    <li key={item.chunk_id}>
                      <button 
                        onClick={() => {
                          onCitationClick(item.chunk_id);
                          if (window.innerWidth < 768) {
                            onClose();
                          }
                        }}
                        className="text-sm font-serif text-[#8D6E63] hover:text-[#5D4037] hover:underline text-left"
                      >
                        {item.citation || item.verse_ref || `Vol ${item.volume}, p. ${item.page_number}`}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
        
        {!loading && !error && data && sortedKeys.length === 0 && (
          <div className="text-center text-[#8D6E63] text-sm font-ui py-8">
            No matrix data found.
          </div>
        )}
      </div>
    </div>
    </>
  );
};
