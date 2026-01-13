'use client';

import { useState, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Loader2, Globe, ArrowRight, Lightbulb, Sparkles, Upload, FileText, CheckCircle, AlertCircle, X, Play } from 'lucide-react';
import Link from 'next/link';
import { api, type CreateJobRequest, type CSVUploadResponse } from '@/lib/api';

interface UploadState {
  file: File | null;
  status: 'idle' | 'uploading' | 'success' | 'error';
  result: CSVUploadResponse | null;
  error: string | null;
}

function FileDropzone({
  label,
  site,
  uploadState,
  onFileSelect,
  onUpload,
  onClear,
  disabled,
  jobId,
}: {
  label: string;
  site: 'site_a' | 'site_b';
  uploadState: UploadState;
  onFileSelect: (file: File) => void;
  onUpload: () => void;
  onClear: () => void;
  disabled: boolean;
  jobId: string | null;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && file.name.endsWith('.csv')) {
      onFileSelect(file);
    }
  }, [onFileSelect]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onFileSelect(file);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-[rgb(var(--text-primary))]">{label}</span>
        {uploadState.status === 'success' && (
          <span className="flex items-center gap-1 text-xs text-green-400">
            <CheckCircle className="w-3 h-3" />
            {uploadState.result?.uploaded} products uploaded
          </span>
        )}
      </div>

      {uploadState.status === 'idle' && !uploadState.file && (
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`
            relative cursor-pointer border-2 border-dashed rounded-xl p-6 text-center transition-all
            ${isDragging
              ? 'border-[rgb(var(--accent))] bg-[rgba(var(--accent),0.1)]'
              : 'border-[rgba(var(--border),var(--border-opacity))] hover:border-[rgb(var(--accent))] hover:bg-[rgba(var(--accent),0.05)]'
            }
            ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
          `}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".csv"
            onChange={handleFileChange}
            className="hidden"
            disabled={disabled}
          />
          <Upload className="w-8 h-8 mx-auto mb-2 text-[rgb(var(--text-muted))]" />
          <p className="text-sm text-[rgb(var(--text-secondary))]">
            Drop CSV file here or <span className="text-[rgb(var(--accent))]">browse</span>
          </p>
          <p className="text-xs text-[rgb(var(--text-muted))] mt-1">
            Required: url column. Optional: title, brand, category, price
          </p>
        </div>
      )}

      {uploadState.file && uploadState.status === 'idle' && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-[rgba(var(--surface-0),0.5)] border border-[rgba(var(--border),var(--border-opacity))]">
          <FileText className="w-8 h-8 text-[rgb(var(--accent))]" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-[rgb(var(--text-primary))] truncate">
              {uploadState.file.name}
            </p>
            <p className="text-xs text-[rgb(var(--text-muted))]">
              {(uploadState.file.size / 1024).toFixed(1)} KB
            </p>
          </div>
          <button
            onClick={onClear}
            className="p-1 rounded-lg hover:bg-[rgba(var(--border),0.3)] transition-colors"
          >
            <X className="w-4 h-4 text-[rgb(var(--text-muted))]" />
          </button>
          <button
            onClick={onUpload}
            disabled={!jobId || disabled}
            className="btn-primary text-sm px-4 py-2"
          >
            Upload
          </button>
        </div>
      )}

      {uploadState.status === 'uploading' && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-[rgba(var(--accent),0.1)] border border-[rgba(var(--accent),0.3)]">
          <Loader2 className="w-6 h-6 animate-spin text-[rgb(var(--accent))]" />
          <span className="text-sm text-[rgb(var(--text-secondary))]">
            Uploading {uploadState.file?.name}...
          </span>
        </div>
      )}

      {uploadState.status === 'success' && (
        <div className="p-4 rounded-xl bg-green-500/10 border border-green-500/30">
          <div className="flex items-center gap-3">
            <CheckCircle className="w-6 h-6 text-green-400" />
            <div className="flex-1">
              <p className="text-sm font-medium text-green-400">
                Successfully uploaded {uploadState.result?.uploaded} products
              </p>
              {uploadState.result?.failed && uploadState.result.failed > 0 && (
                <p className="text-xs text-yellow-400 mt-1">
                  {uploadState.result.failed} rows failed
                </p>
              )}
            </div>
            <button
              onClick={onClear}
              className="text-xs text-[rgb(var(--text-muted))] hover:text-[rgb(var(--text-secondary))]"
            >
              Upload different file
            </button>
          </div>
        </div>
      )}

      {uploadState.status === 'error' && (
        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-6 h-6 text-red-400" />
            <div className="flex-1">
              <p className="text-sm text-red-400">{uploadState.error}</p>
            </div>
            <button
              onClick={onClear}
              className="text-xs text-[rgb(var(--text-muted))] hover:text-[rgb(var(--text-secondary))]"
            >
              Try again
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function NewJobPage() {
  const router = useRouter();
  const [step, setStep] = useState<'create' | 'upload'>('create');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [runningJob, setRunningJob] = useState(false);

  const [formData, setFormData] = useState<CreateJobRequest>({
    name: '',
    site1_url: '',
    site2_url: '',
    site1_category: '',
    site2_category: '',
    ai_validation_enabled: false,
    ai_validation_min: 0.70,
    ai_validation_max: 0.90,
    ai_validation_cap: 100,
    embed_enriched_text: false,
    token_norm_v2: false,
    use_brand_ontology: false,
    use_category_ontology: false,
    use_variant_extractor: false,
    use_ocr_text: false,
  });

  const [siteAUpload, setSiteAUpload] = useState<UploadState>({
    file: null,
    status: 'idle',
    result: null,
    error: null,
  });

  const [siteBUpload, setSiteBUpload] = useState<UploadState>({
    file: null,
    status: 'idle',
    result: null,
    error: null,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      setLoading(true);
      setError(null);

      const job = await api.jobs.create({
        ...formData,
        site1_category: formData.site1_category || undefined,
        site2_category: formData.site2_category || undefined,
      });

      setJobId(job.id);
      setStep('upload');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create job');
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleUpload = async (site: 'site_a' | 'site_b') => {
    const uploadState = site === 'site_a' ? siteAUpload : siteBUpload;
    const setUploadState = site === 'site_a' ? setSiteAUpload : setSiteBUpload;

    if (!uploadState.file || !jobId) return;

    setUploadState(prev => ({ ...prev, status: 'uploading' }));

    try {
      const result = await api.upload.csv(jobId, site, uploadState.file);
      setUploadState(prev => ({ ...prev, status: 'success', result }));
    } catch (err) {
      setUploadState(prev => ({
        ...prev,
        status: 'error',
        error: err instanceof Error ? err.message : 'Upload failed',
      }));
    }
  };

  const handleRunMatching = async () => {
    if (!jobId) return;

    setRunningJob(true);
    try {
      await api.jobs.run(jobId);
      router.push(`/jobs/${jobId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start matching');
      setRunningJob(false);
    }
  };

  const canRunMatching = siteAUpload.status === 'success' && siteBUpload.status === 'success';

  return (
    <div className="max-w-3xl mx-auto space-y-8 animate-fade-in">
      {/* Header */}
      <div className="space-y-4">
        <Link
          href="/jobs"
          className="nav-link inline-flex items-center gap-2 text-sm"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Jobs
        </Link>
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight text-[rgb(var(--text-primary))]">
            {step === 'create' ? 'Create New Job' : 'Upload Product Data'}
          </h1>
          <p className="text-[rgb(var(--text-secondary))]">
            {step === 'create'
              ? 'Set up a new product matching job between two e-commerce websites'
              : 'Upload CSV files with product URLs for both sites'
            }
          </p>
        </div>
      </div>

      {/* Step Indicator */}
      <div className="flex items-center gap-4">
        <div className={`flex items-center gap-2 ${step === 'create' ? 'text-[rgb(var(--accent))]' : 'text-green-400'}`}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
            step === 'create' ? 'bg-[rgb(var(--accent))] text-black' : 'bg-green-500 text-white'
          }`}>
            {step === 'upload' ? <CheckCircle className="w-5 h-5" /> : '1'}
          </div>
          <span className="text-sm font-medium">Create Job</span>
        </div>
        <div className="flex-1 h-px bg-[rgba(var(--border),var(--border-opacity))]" />
        <div className={`flex items-center gap-2 ${step === 'upload' ? 'text-[rgb(var(--accent))]' : 'text-[rgb(var(--text-muted))]'}`}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
            step === 'upload' ? 'bg-[rgb(var(--accent))] text-black' : 'bg-[rgb(var(--surface-2))] text-[rgb(var(--text-muted))]'
          }`}>
            2
          </div>
          <span className="text-sm font-medium">Upload & Run</span>
        </div>
      </div>

      {step === 'create' && (
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="glass-card p-6 space-y-6">
            {/* Job Name */}
            <div className="space-y-2">
              <label htmlFor="name" className="block text-sm font-medium text-[rgb(var(--text-primary))]">
                Job Name
                <span className="text-red-400 ml-1">*</span>
              </label>
              <input
                type="text"
                id="name"
                name="name"
                required
                value={formData.name}
                onChange={handleChange}
                className="input-field"
                placeholder="e.g., Nykaa vs Purplle Lipsticks"
              />
            </div>

            {/* Site URLs Section */}
            <div className="relative">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Source Site */}
                <div className="space-y-4 p-4 rounded-xl bg-[rgba(var(--surface-0),0.5)]">
                  <div className="flex items-center gap-2 text-[rgb(var(--text-secondary))]">
                    <Globe className="w-4 h-4" />
                    <span className="text-sm font-medium">Source Site (Your Products)</span>
                  </div>
                  <div className="space-y-2">
                    <label htmlFor="site1_url" className="block text-sm font-medium text-[rgb(var(--text-primary))]">
                      Base URL
                      <span className="text-red-400 ml-1">*</span>
                    </label>
                    <input
                      type="url"
                      id="site1_url"
                      name="site1_url"
                      required
                      value={formData.site1_url}
                      onChange={handleChange}
                      className="input-field font-mono text-sm"
                      placeholder="https://nykaa.com"
                    />
                  </div>
                  <div className="space-y-2">
                    <label htmlFor="site1_category" className="block text-sm text-[rgb(var(--text-muted))]">
                      Category
                      <span className="text-[rgb(var(--text-muted))] text-xs ml-1">(optional)</span>
                    </label>
                    <input
                      type="text"
                      id="site1_category"
                      name="site1_category"
                      value={formData.site1_category}
                      onChange={handleChange}
                      className="input-field"
                      placeholder="e.g., Lipstick"
                    />
                  </div>
                </div>

                {/* Arrow Divider */}
                <div className="hidden md:flex absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10">
                  <div className="p-3 rounded-full bg-[rgb(var(--surface-2))] border border-[rgba(var(--border),var(--border-opacity))]">
                    <ArrowRight className="w-5 h-5 text-[rgb(var(--accent))]" />
                  </div>
                </div>

                {/* Target Site */}
                <div className="space-y-4 p-4 rounded-xl bg-[rgba(var(--surface-0),0.5)]">
                  <div className="flex items-center gap-2 text-[rgb(var(--text-secondary))]">
                    <Globe className="w-4 h-4" />
                    <span className="text-sm font-medium">Target Site (Competitor)</span>
                  </div>
                  <div className="space-y-2">
                    <label htmlFor="site2_url" className="block text-sm font-medium text-[rgb(var(--text-primary))]">
                      Base URL
                      <span className="text-red-400 ml-1">*</span>
                    </label>
                    <input
                      type="url"
                      id="site2_url"
                      name="site2_url"
                      required
                      value={formData.site2_url}
                      onChange={handleChange}
                      className="input-field font-mono text-sm"
                      placeholder="https://purplle.com"
                    />
                  </div>
                  <div className="space-y-2">
                    <label htmlFor="site2_category" className="block text-sm text-[rgb(var(--text-muted))]">
                      Category
                      <span className="text-[rgb(var(--text-muted))] text-xs ml-1">(optional)</span>
                    </label>
                    <input
                      type="text"
                      id="site2_category"
                      name="site2_category"
                      value={formData.site2_category}
                      onChange={handleChange}
                      className="input-field"
                      placeholder="e.g., Lipstick"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* AI Validation Options */
            <div className="space-y-3 p-4 rounded-xl bg-[rgba(var(--surface-0),0.5)] border border-[rgba(var(--border),var(--border-opacity))]">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-[rgb(var(--text-primary))]">Enable AI Validation</label>
                <input
                  type="checkbox"
                  checked={formData.ai_validation_enabled}
                  onChange={(e) => setFormData(prev => ({ ...prev, ai_validation_enabled: e.target.checked }))}
                  className="toggle-checkbox"
                />
              </div>
              {formData.ai_validation_enabled && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs text-[rgb(var(--text-muted))]">Min Score</label>
                    <input
                      type="number"
                      min={0}
                      max={1}
                      step={0.01}
                      value={formData.ai_validation_min}
                      onChange={(e) => setFormData(prev => ({ ...prev, ai_validation_min: parseFloat(e.target.value) }))}
                      className="input-field"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-[rgb(var(--text-muted))]">Max Score</label>
                    <input
                      type="number"
                      min={0}
                      max={1}
                      step={0.01}
                      value={formData.ai_validation_max}
                      onChange={(e) => setFormData(prev => ({ ...prev, ai_validation_max: parseFloat(e.target.value) }))}
                      className="input-field"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-[rgb(var(--text-muted))]">Cap / Job</label>
                    <input
                      type="number"
                      min={0}
                      step={1}
                      value={formData.ai_validation_cap}
                      onChange={(e) => setFormData(prev => ({ ...prev, ai_validation_cap: parseInt(e.target.value || '0', 10) }))}
                      className="input-field"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Text Matching Options */}
            <div className="space-y-3 p-4 rounded-xl bg-[rgba(var(--surface-0),0.5)] border border-[rgba(var(--border),var(--border-opacity))]">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-[rgb(var(--text-primary))]">Embed Enriched Text (title + brand + category)</label>
                <input
                  type="checkbox"
                  checked={formData.embed_enriched_text}
                  onChange={(e) => setFormData(prev => ({ ...prev, embed_enriched_text: e.target.checked }))}
                  className="toggle-checkbox"
                />
              </div>
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-[rgb(var(--text-primary))]">Improved Token Normalization (v2)</label>
                <input
                  type="checkbox"
                  checked={formData.token_norm_v2}
                  onChange={(e) => setFormData(prev => ({ ...prev, token_norm_v2: e.target.checked }))}
                  className="toggle-checkbox"
                />
              </div>
            </div>

            {/* Ontologies & Variants */}
            <div className="space-y-3 p-4 rounded-xl bg-[rgba(var(--surface-0),0.5)] border border-[rgba(var(--border),var(--border-opacity))]">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-[rgb(var(--text-primary))]">Use Brand Ontology</label>
                <input
                  type="checkbox"
                  checked={formData.use_brand_ontology}
                  onChange={(e) => setFormData(prev => ({ ...prev, use_brand_ontology: e.target.checked }))}
                />
              </div>
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-[rgb(var(--text-primary))]">Use Category Ontology</label>
                <input
                  type="checkbox"
                  checked={formData.use_category_ontology}
                  onChange={(e) => setFormData(prev => ({ ...prev, use_category_ontology: e.target.checked }))}
                />
              </div>
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-[rgb(var(--text-primary))]">Variant Extractor (size/shade/model)</label>
                <input
                  type="checkbox"
                  checked={formData.use_variant_extractor}
                  onChange={(e) => setFormData(prev => ({ ...prev, use_variant_extractor: e.target.checked }))}
                />
              </div>
            </div>

            {/* Error Message */}
            {error && (
              <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20">
                <p className="text-sm text-red-400">{error}</p>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-4 pt-6 border-t border-[rgba(var(--border),var(--border-opacity))]">
              <button
                type="submit"
                disabled={loading}
                className="btn-primary flex-1 flex items-center justify-center gap-2"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    Continue to Upload
                  </>
                )}
              </button>
              <Link href="/jobs" className="btn-secondary">
                Cancel
              </Link>
            </div>
          </div>

          {/* Tips Card */}
          <div className="elevated-card p-5">
            <div className="flex items-start gap-4">
              <div className="p-2 rounded-lg bg-[rgba(var(--accent),0.1)]">
                <Lightbulb className="w-5 h-5 text-[rgb(var(--accent))]" />
              </div>
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-[rgb(var(--text-primary))]">
                  Tips for Better Matching
                </h3>
                <ul className="text-sm text-[rgb(var(--text-muted))] space-y-1.5">
                  <li className="flex items-start gap-2">
                    <span className="text-[rgb(var(--accent))]">•</span>
                    Prepare CSV files with product URLs from both sites
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-[rgb(var(--accent))]">•</span>
                    Include title, brand, and category columns for better matching accuracy
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-[rgb(var(--accent))]">•</span>
                    Ensure both sites sell similar product types
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </form>
      )}

      {step === 'upload' && (
        <div className="space-y-6">
          <div className="glass-card p-6 space-y-6">
            <div className="p-4 rounded-xl bg-[rgba(var(--accent),0.1)] border border-[rgba(var(--accent),0.2)]">
              <p className="text-sm text-[rgb(var(--text-secondary))]">
                <strong className="text-[rgb(var(--accent))]">Job Created!</strong> Now upload CSV files containing product URLs for both sites.
              </p>
            </div>

            {/* Site A Upload */}
            <div className="space-y-4 p-4 rounded-xl bg-[rgba(var(--surface-0),0.5)]">
              <div className="flex items-center gap-2 text-[rgb(var(--text-secondary))]">
                <Globe className="w-4 h-4" />
                <span className="text-sm font-medium">Source Site Products</span>
                <span className="text-xs text-[rgb(var(--text-muted))]">({formData.site1_url})</span>
              </div>
              <FileDropzone
                label="Upload Site A CSV"
                site="site_a"
                uploadState={siteAUpload}
                onFileSelect={(file) => setSiteAUpload({ file, status: 'idle', result: null, error: null })}
                onUpload={() => handleUpload('site_a')}
                onClear={() => setSiteAUpload({ file: null, status: 'idle', result: null, error: null })}
                disabled={siteAUpload.status === 'uploading'}
                jobId={jobId}
              />
            </div>

            {/* Site B Upload */}
            <div className="space-y-4 p-4 rounded-xl bg-[rgba(var(--surface-0),0.5)]">
              <div className="flex items-center gap-2 text-[rgb(var(--text-secondary))]">
                <Globe className="w-4 h-4" />
                <span className="text-sm font-medium">Target Site Products (Catalog)</span>
                <span className="text-xs text-[rgb(var(--text-muted))]">({formData.site2_url})</span>
              </div>
              <FileDropzone
                label="Upload Site B CSV"
                site="site_b"
                uploadState={siteBUpload}
                onFileSelect={(file) => setSiteBUpload({ file, status: 'idle', result: null, error: null })}
                onUpload={() => handleUpload('site_b')}
                onClear={() => setSiteBUpload({ file: null, status: 'idle', result: null, error: null })}
                disabled={siteBUpload.status === 'uploading'}
                jobId={jobId}
              />
            </div>

            {/* Error Message */}
            {error && (
              <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20">
                <p className="text-sm text-red-400">{error}</p>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-4 pt-6 border-t border-[rgba(var(--border),var(--border-opacity))]">
              <button
                onClick={handleRunMatching}
                disabled={!canRunMatching || runningJob}
                className={`btn-primary flex-1 flex items-center justify-center gap-2 ${
                  !canRunMatching ? 'opacity-50 cursor-not-allowed' : ''
                }`}
              >
                {runningJob ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Starting...
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4" />
                    Run Product Matching
                  </>
                )}
              </button>
              <Link href={`/jobs/${jobId}`} className="btn-secondary">
                View Job
              </Link>
            </div>
          </div>

          {/* CSV Format Help */}
          <div className="elevated-card p-5">
            <div className="flex items-start gap-4">
              <div className="p-2 rounded-lg bg-[rgba(var(--accent),0.1)]">
                <FileText className="w-5 h-5 text-[rgb(var(--accent))]" />
              </div>
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-[rgb(var(--text-primary))]">
                  CSV File Format
                </h3>
                <div className="text-sm text-[rgb(var(--text-muted))] space-y-2">
                  <p>Your CSV file should have the following columns:</p>
                  <div className="font-mono text-xs bg-[rgb(var(--surface-2))] p-3 rounded-lg overflow-x-auto">
                    <div className="text-green-400">url,title,brand,category,price</div>
                    <div className="text-[rgb(var(--text-muted))]">https://site.com/product/123,Product Name,Brand,Category,599</div>
                  </div>
                  <p className="text-xs">
                    <strong className="text-[rgb(var(--accent))]">Required:</strong> url |
                    <strong className="text-[rgb(var(--text-secondary))]"> Optional:</strong> title, brand, category, price
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
