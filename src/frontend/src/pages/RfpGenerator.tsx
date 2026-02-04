/**
 * RFP Generator Page
 * Generates RFP response documents based on opportunity data and company information.
 * Phase 1: Template-based generation (no AI yet)
 */
import { useState, useEffect, useMemo, useRef } from 'react';
import {
  FileText,
  Building2,
  Search,
  Filter,
  Loader2,
  Download,
  Sparkles,
  Save,
  CheckCircle,
  AlertCircle,
  ChevronDown,
} from 'lucide-react';
import { opportunitiesApi, companyApi, rfpGeneratorApi } from '../services/api';
import type { Opportunity, GenerateRfpResponse } from '../types';
import Markdown from 'react-markdown';

// Category options for filtering
const CATEGORY_OPTIONS = [
  { value: '', label: 'All Categories' },
  { value: 'dynamics_365', label: 'Dynamics 365' },
  { value: 'ai', label: 'AI / Machine Learning' },
  { value: 'iot', label: 'IoT' },
  { value: 'erp', label: 'ERP Systems' },
  { value: 'staff_augmentation', label: 'Staff Augmentation' },
  { value: 'other_it', label: 'Other IT' },
];

interface Message {
  type: 'success' | 'error';
  text: string;
}

interface CompanyFormData {
  company_name: string;
  company_bio: string;
  relevant_experience: string;
  certifications: string;
}

export function RfpGenerator() {
  // Opportunity state
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [loadingOpportunities, setLoadingOpportunities] = useState(true);
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Company info state
  const [companyData, setCompanyData] = useState<CompanyFormData>({
    company_name: '',
    company_bio: '',
    relevant_experience: '',
    certifications: '',
  });
  const [loadingCompany, setLoadingCompany] = useState(true);
  const [savingCompany, setSavingCompany] = useState(false);

  // Generation state
  const [generating, setGenerating] = useState(false);
  const [generatedContent, setGeneratedContent] = useState<GenerateRfpResponse | null>(null);
  const [downloading, setDownloading] = useState(false);

  // Messages
  const [message, setMessage] = useState<Message | null>(null);

  // Fetch opportunities on mount
  useEffect(() => {
    const fetchOpportunities = async () => {
      try {
        setLoadingOpportunities(true);
        const response = await opportunitiesApi.list(1, 100);
        setOpportunities(response.items);
      } catch (error) {
        console.error('Error fetching opportunities:', error);
        setMessage({ type: 'error', text: 'Failed to load opportunities' });
      } finally {
        setLoadingOpportunities(false);
      }
    };
    fetchOpportunities();
  }, []);

  // Fetch company info on mount
  useEffect(() => {
    const fetchCompanyInfo = async () => {
      try {
        setLoadingCompany(true);
        const data = await companyApi.get();
        if (data) {
          setCompanyData({
            company_name: data.company_name || '',
            company_bio: data.company_bio || '',
            relevant_experience: data.relevant_experience || '',
            certifications: data.certifications?.join(', ') || '',
          });
        }
      } catch (error) {
        console.error('Error fetching company info:', error);
      } finally {
        setLoadingCompany(false);
      }
    };
    fetchCompanyInfo();
  }, []);

  // Filter opportunities based on search and category
  const filteredOpportunities = useMemo(() => {
    return opportunities.filter((opp) => {
      const matchesSearch =
        !searchQuery ||
        opp.title.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory =
        !categoryFilter ||
        opp.category?.toLowerCase() === categoryFilter.toLowerCase();
      return matchesSearch && matchesCategory;
    });
  }, [opportunities, searchQuery, categoryFilter]);

  // Get selected opportunity (for potential future use)
  const _selectedOpportunity = useMemo(() => {
    return opportunities.find((o) => o.id === selectedOpportunityId);
  }, [opportunities, selectedOpportunityId]);
  void _selectedOpportunity; // Suppress unused warning

  // Handle click outside to close dropdown
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Handle opportunity selection from dropdown
  const handleSelectOpportunity = (opp: Opportunity) => {
    setSelectedOpportunityId(opp.id);
    setSearchQuery(opp.title);
    setShowDropdown(false);
  };

  // Handle company info change
  const handleCompanyChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setCompanyData((prev) => ({ ...prev, [name]: value }));
  };

  // Save company info
  const handleSaveCompany = async () => {
    try {
      setSavingCompany(true);
      setMessage(null);
      await companyApi.update({
        company_name: companyData.company_name,
        company_bio: companyData.company_bio || null,
        relevant_experience: companyData.relevant_experience || null,
        certifications: companyData.certifications
          ? companyData.certifications.split(',').map((c) => c.trim()).filter(Boolean)
          : [],
      });
      setMessage({ type: 'success', text: 'Company information saved!' });
    } catch (error) {
      console.error('Error saving company info:', error);
      setMessage({ type: 'error', text: 'Failed to save company information' });
    } finally {
      setSavingCompany(false);
    }
  };

  // Generate RFP response
  const handleGenerate = async () => {
    if (!selectedOpportunityId || !companyData.company_name) {
      setMessage({ type: 'error', text: 'Please select an opportunity and enter company name' });
      return;
    }

    try {
      setGenerating(true);
      setMessage(null);
      setGeneratedContent(null);

      const response = await rfpGeneratorApi.generate({
        opportunity_id: selectedOpportunityId,
        company_info: {
          company_name: companyData.company_name,
          company_bio: companyData.company_bio || null,
          relevant_experience: companyData.relevant_experience || null,
          certifications: companyData.certifications
            ? companyData.certifications.split(',').map((c) => c.trim()).filter(Boolean)
            : [],
        },
      });

      setGeneratedContent(response);
      setMessage({ type: 'success', text: 'RFP response generated successfully!' });
    } catch (error) {
      console.error('Error generating RFP:', error);
      setMessage({ type: 'error', text: 'Failed to generate RFP response' });
    } finally {
      setGenerating(false);
    }
  };

  // Download generated document
  const handleDownload = async () => {
    if (!generatedContent || !selectedOpportunityId) return;

    try {
      setDownloading(true);
      setMessage(null);

      const blob = await rfpGeneratorApi.download({
        document_content: generatedContent.document_content,
        opportunity_id: selectedOpportunityId,
        format: 'docx',
        opportunity_title: generatedContent.opportunity_title,
      });

      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const filename = `${generatedContent.opportunity_title?.replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').toLowerCase() || 'rfp-response'}-response.docx`;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      setMessage({ type: 'success', text: 'Document downloaded!' });
    } catch (error) {
      console.error('Error downloading document:', error);
      setMessage({ type: 'error', text: 'Failed to download document' });
    } finally {
      setDownloading(false);
    }
  };

  // Format deadline for display
  const formatDeadline = (deadline: string | null) => {
    if (!deadline) return 'No deadline';
    return new Date(deadline).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 p-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 bg-violet-100 dark:bg-violet-900/30 rounded-lg">
            <FileText className="h-6 w-6 text-violet-600 dark:text-violet-400" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
            RFP Generator
          </h1>
        </div>
        <p className="text-slate-600 dark:text-slate-400">
          Generate professional RFP response documents based on opportunity data
        </p>
      </div>

      {/* Message Banner */}
      {message && (
        <div
          className={`mb-6 p-4 rounded-lg flex items-center gap-3 ${
            message.type === 'success'
              ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200'
              : 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200'
          }`}
        >
          {message.type === 'success' ? (
            <CheckCircle className="h-5 w-5" />
          ) : (
            <AlertCircle className="h-5 w-5" />
          )}
          <span>{message.text}</span>
        </div>
      )}

      {/* Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column - Input Form */}
        <div className="space-y-6">
          {/* Section 1: Select Opportunity */}
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-6">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
              <Search className="h-5 w-5 text-violet-600 dark:text-violet-400" />
              Select Opportunity
            </h2>

            {/* Search Input with Dropdown */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              {/* Search Input with Typeahead Dropdown */}
              <div className="relative" ref={dropdownRef}>
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400 z-10" />
                <input
                  type="text"
                  placeholder="Search opportunities..."
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setShowDropdown(true);
                    // Clear selection if user is typing a new search
                    if (selectedOpportunityId) {
                      const selected = opportunities.find(o => o.id === selectedOpportunityId);
                      if (selected && e.target.value !== selected.title) {
                        setSelectedOpportunityId('');
                      }
                    }
                  }}
                  onFocus={() => setShowDropdown(true)}
                  className="w-full pl-10 pr-4 py-2 bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                />

                {/* Typeahead Dropdown */}
                {showDropdown && !loadingOpportunities && (
                  <div className="absolute z-20 w-full mt-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-lg shadow-lg max-h-64 overflow-y-auto">
                    {filteredOpportunities.length === 0 ? (
                      <div className="p-3 text-sm text-slate-500 dark:text-slate-400">
                        No opportunities match your search
                      </div>
                    ) : (
                      filteredOpportunities.map((opp) => (
                        <button
                          key={opp.id}
                          type="button"
                          onClick={() => handleSelectOpportunity(opp)}
                          className={`w-full text-left px-4 py-3 hover:bg-violet-50 dark:hover:bg-slate-700 border-b border-slate-100 dark:border-slate-700 last:border-b-0 transition-colors ${
                            selectedOpportunityId === opp.id ? 'bg-violet-50 dark:bg-slate-700' : ''
                          }`}
                        >
                          <div className="font-medium text-slate-900 dark:text-white text-sm">
                            {opp.title}
                          </div>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-xs px-2 py-0.5 bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 rounded">
                              {opp.category || 'Uncategorized'}
                            </span>
                            <span className="text-xs text-slate-500 dark:text-slate-400">
                              {formatDeadline(opp.submission_deadline)}
                            </span>
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>

              {/* Category Filter */}
              <div className="relative">
                <Filter className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                <select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  className="w-full pl-10 pr-8 py-2 bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-900 dark:text-white appearance-none focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                >
                  {CATEGORY_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
              </div>
            </div>

            {/* Loading State */}
            {loadingOpportunities && (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-5 w-5 animate-spin text-violet-600" />
                <span className="ml-2 text-slate-500">Loading opportunities...</span>
              </div>
            )}

            {/* Selected Opportunity Display */}
            {selectedOpportunityId && !loadingOpportunities && (
              <div className="p-3 bg-violet-50 dark:bg-violet-900/20 border border-violet-200 dark:border-violet-800 rounded-lg">
                <div className="flex items-center gap-2">
                  <CheckCircle className="h-4 w-4 text-violet-600 dark:text-violet-400" />
                  <span className="text-sm font-medium text-violet-800 dark:text-violet-200">
                    Selected: {opportunities.find(o => o.id === selectedOpportunityId)?.title}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Section 2: Company Information */}
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-6">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
              <Building2 className="h-5 w-5 text-violet-600 dark:text-violet-400" />
              Company Information
            </h2>

            {loadingCompany ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-violet-600" />
                <span className="ml-2 text-slate-500">Loading company info...</span>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Company Name */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Company Name *
                  </label>
                  <input
                    type="text"
                    name="company_name"
                    value={companyData.company_name}
                    onChange={handleCompanyChange}
                    placeholder="Enter company name"
                    className="w-full p-3 bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                  />
                </div>

                {/* Company Bio */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Company Bio
                  </label>
                  <textarea
                    name="company_bio"
                    value={companyData.company_bio}
                    onChange={handleCompanyChange}
                    rows={3}
                    placeholder="Brief description of your company..."
                    className="w-full p-3 bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-violet-500 focus:border-transparent resize-none"
                  />
                </div>

                {/* Relevant Experience */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Relevant Experience
                  </label>
                  <textarea
                    name="relevant_experience"
                    value={companyData.relevant_experience}
                    onChange={handleCompanyChange}
                    rows={3}
                    placeholder="Describe your relevant past projects and experience..."
                    className="w-full p-3 bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-violet-500 focus:border-transparent resize-none"
                  />
                </div>

                {/* Certifications */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Certifications (comma-separated)
                  </label>
                  <input
                    type="text"
                    name="certifications"
                    value={companyData.certifications}
                    onChange={handleCompanyChange}
                    placeholder="e.g., ISO 27001, SOC 2, AWS Partner"
                    className="w-full p-3 bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                  />
                </div>

                {/* Save Button */}
                <button
                  onClick={handleSaveCompany}
                  disabled={savingCompany}
                  className="flex items-center gap-2 px-4 py-2 bg-slate-600 hover:bg-slate-700 disabled:bg-slate-400 text-white rounded-lg transition-colors"
                >
                  {savingCompany ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  Save Company Info
                </button>
              </div>
            )}
          </div>

          {/* Section 3: Generate Button */}
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-6">
            <button
              onClick={handleGenerate}
              disabled={generating || !selectedOpportunityId || !companyData.company_name}
              className="relative w-full overflow-hidden flex items-center justify-center gap-3 px-6 py-4 bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-700 hover:to-purple-700 disabled:from-slate-400 disabled:to-slate-400 text-white font-semibold rounded-xl shadow-lg transition-all"
            >
              {/* Progress bar animation overlay when generating */}
              {generating && (
                <div
                  className="absolute inset-0 bg-gradient-to-r from-violet-400/50 to-purple-400/50"
                  style={{
                    animation: 'progressFill 30s ease-in-out forwards',
                    transformOrigin: 'left',
                  }}
                />
              )}
              <span className="relative z-10 flex items-center gap-3">
                {generating ? (
                  <>
                    <Loader2 className="h-5 w-5 animate-spin" />
                    Generating RFP Response...
                  </>
                ) : (
                  <>
                    <Sparkles className="h-5 w-5" />
                    Generate RFP Response
                  </>
                )}
              </span>
            </button>
            {!selectedOpportunityId && (
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400 text-center">
                Please select an opportunity to generate a response
              </p>
            )}
            {/* CSS animation keyframes */}
            <style>{`
              @keyframes progressFill {
                0% {
                  transform: scaleX(0);
                }
                10% {
                  transform: scaleX(0.1);
                }
                30% {
                  transform: scaleX(0.3);
                }
                50% {
                  transform: scaleX(0.5);
                }
                70% {
                  transform: scaleX(0.7);
                }
                90% {
                  transform: scaleX(0.85);
                }
                100% {
                  transform: scaleX(0.95);
                }
              }
            `}</style>
          </div>
        </div>

        {/* Right Column - Preview Panel */}
        <div className="space-y-6">
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-6 h-[calc(100vh-200px)] min-h-[600px] max-h-[900px] flex flex-col">
            <div className="flex items-center justify-between mb-4 flex-shrink-0">
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                <FileText className="h-5 w-5 text-violet-600 dark:text-violet-400" />
                Preview
              </h2>

              {/* Download Button */}
              <button
                onClick={handleDownload}
                disabled={downloading || !generatedContent}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-slate-400 text-white rounded-lg transition-colors"
              >
                {downloading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                Download DOCX
              </button>
            </div>

            {/* Preview Content - Scrollable */}
            <div className="flex-1 overflow-y-auto overflow-x-hidden pr-2">
              {generatedContent ? (
                <div className="prose dark:prose-invert prose-sm max-w-none text-slate-900 dark:text-white">
                  <Markdown>{generatedContent.document_content}</Markdown>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center text-slate-500 dark:text-slate-400">
                  <FileText className="h-16 w-16 mb-4 opacity-30" />
                  <p className="text-lg font-medium">No document generated yet</p>
                  <p className="text-sm mt-1">
                    Select an opportunity and click Generate to preview the RFP response
                  </p>
                </div>
              )}
            </div>

            {generatedContent && (
              <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-700 text-xs text-slate-500 dark:text-slate-400 flex-shrink-0">
                Generated: {new Date(generatedContent.generated_at).toLocaleString()}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

