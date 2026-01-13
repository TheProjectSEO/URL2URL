'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  Play,
  RefreshCw,
  ExternalLink,
  Trash2,
  Globe,
  ArrowRight,
  Package,
  GitCompareArrows,
  Percent,
  Clock,
  Loader2,
  Settings,
  Wand2
} from 'lucide-react';
import { api, type Job, type Match, type CSVUploadResponse } from '@/lib/api';
import { formatRelativeTime } from '@/lib/utils';
import ProgressBar from '@/components/ProgressBar';
import MatchTable from '@/components/MatchTable';
import { CSVUploader } from '@/components/CSVUploader';

// Get status badge class
function getStatusBadgeClass(status: string): string {
  const statusMap: Record<string, string> = {
    pending: 'badge-pending',
    running: 'badge-running',
    completed: 'badge-completed',
    failed: 'badge-failed',
  };
  return statusMap[status] || 'badge-pending';
}

function StatItem({ icon: Icon, label, value }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-[rgba(var(--border),var(--border-opacity))] last:border-0">
      <div className="flex items-center gap-2 text-[rgb(var(--text-muted))]">
        <Icon className="w-4 h-4" />
        <span className="text-sm">{label}</span>
      </div>
      <span className="text-sm font-medium text-[rgb(var(--text-primary))]">{value}</span>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="text-center space-y-4">
        <div className="relative">
          <div className="absolute inset-0 bg-[rgb(var(--accent))] blur-2xl opacity-20 animate-pulse" />
          <Loader2 className="w-10 h-10 text-[rgb(var(--accent))] animate-spin relative" />
        </div>
        <p className="text-[rgb(var(--text-muted))] text-sm">Loading job details...</p>
      </div>
    </div>
  );
}

export default function JobDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = params.id as string;

  const [job, setJob] = useState<Job | null>(null);
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [metrics, setMetrics] = useState<any>({});
  // AI settings local state
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiMin, setAiMin] = useState(0.7);
  const [aiMax, setAiMax] = useState(0.9);
  const [aiCap, setAiCap] = useState(100);
  // Quick match state
  const [qmTitle, setQmTitle] = useState('');
  const [qmUrl, setQmUrl] = useState('');
  const [qmBrand, setQmBrand] = useState('');
  const [qmCategory, setQmCategory] = useState('');
  const [qmPrice, setQmPrice] = useState('');
  const [qmResults, setQmResults] = useState<any | null>(null);
  const [qmLoading, setQmLoading] = useState(false);
  // Text matching settings
  const [embedEnriched, setEmbedEnriched] = useState(false);
  const [tokenNormV2, setTokenNormV2] = useState(false);
  const [useBrandOnto, setUseBrandOnto] = useState(false);
  const [useCategoryOnto, setUseCategoryOnto] = useState(false);
  const [useVariant, setUseVariant] = useState(false);

  useEffect(() => {
    fetchJobData();
    const interval = setInterval(() => {
      if (job?.status === 'running') {
        fetchJobData(true);
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [jobId, job?.status]);

  const fetchJobData = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      setError(null);

      const [jobData, matchesData] = await Promise.all([
        api.jobs.get(jobId),
        api.jobs.matches(jobId).catch(() => []),
      ]);

      setJob(jobData);
      // Initialize AI settings from config if exists
      const cfg: any = (jobData as any).config || {};
      if (typeof cfg.ai_validation_enabled === 'boolean') setAiEnabled(cfg.ai_validation_enabled);
      if (typeof cfg.ai_validation_min === 'number') setAiMin(cfg.ai_validation_min);
      if (typeof cfg.ai_validation_max === 'number') setAiMax(cfg.ai_validation_max);
      if (typeof cfg.ai_validation_cap === 'number') setAiCap(cfg.ai_validation_cap);
      if (typeof cfg.embed_enriched_text === 'boolean') setEmbedEnriched(cfg.embed_enriched_text);
      if (typeof cfg.token_norm_v2 === 'boolean') setTokenNormV2(cfg.token_norm_v2);
      if (typeof cfg.use_brand_ontology === 'boolean') setUseBrandOnto(cfg.use_brand_ontology);
      if (typeof cfg.use_category_ontology === 'boolean') setUseCategoryOnto(cfg.use_category_ontology);
      if (typeof cfg.use_variant_extractor === 'boolean') setUseVariant(cfg.use_variant_extractor);
      setMatches(matchesData);
      // Fetch persisted matcher metrics
      try {
        const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${base}/api/jobs/${jobId}/metrics`);
        if (res.ok) {
          const m = await res.json();
          setMetrics(m || {});
        }
      } catch (e) {
        // Ignore metrics errors
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load job details');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRunJob = async () => {
    try {
      setRefreshing(true);
      await api.jobs.run(jobId);
      await fetchJobData();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to start job');
      setRefreshing(false);
    }
  };

  const handleDeleteJob = async () => {
    if (!confirm('Are you sure you want to delete this job? This action cannot be undone.')) {
      return;
    }

    try {
      await api.jobs.delete(jobId);
      router.push('/jobs');
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete job');
    }
  };

  const handleApproveMatch = async (matchId: string) => {
    try {
      await api.matches.update(matchId, 'approved');
      setMatches(matches.map(m =>
        m.id === matchId ? { ...m, status: 'approved' as const } : m
      ));
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to approve match');
    }
  };

  const handleRejectMatch = async (matchId: string) => {
    try {
      await api.matches.update(matchId, 'rejected');
      setMatches(matches.map(m =>
        m.id === matchId ? { ...m, status: 'rejected' as const } : m
      ));
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to reject match');
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    fetchJobData();
  };

  if (loading) return <LoadingState />;

  if (error || !job) {
    return (
      <div className="glass-card p-12 text-center animate-fade-in">
        <div className="max-w-md mx-auto space-y-4">
          <p className="text-red-400">{error || 'Job not found'}</p>
          <div className="flex gap-3 justify-center">
            <button onClick={() => fetchJobData()} className="btn-primary">
              Try Again
            </button>
            <Link href="/jobs" className="btn-secondary">
              Back to Jobs
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const matchRate = job.total_products && job.matched_products
    ? Math.round((job.matched_products / job.total_products) * 100)
    : 0;

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="space-y-4">
        <Link href="/jobs" className="nav-link inline-flex items-center gap-2 text-sm">
          <ArrowLeft className="w-4 h-4" />
          Back to Jobs
        </Link>

        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="space-y-2">
            <h1 className="text-3xl font-semibold tracking-tight text-[rgb(var(--text-primary))]">
              {job.name}
            </h1>
            <div className="flex items-center gap-3 text-sm text-[rgb(var(--text-muted))]">
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5" />
                Created {formatRelativeTime(job.created_at)}
              </span>
              {job.updated_at && (
                <>
                  <span className="text-[rgb(var(--text-muted))]">•</span>
                  <span>Updated {formatRelativeTime(job.updated_at)}</span>
                </>
              )}
            </div>
          </div>

          <span className={getStatusBadgeClass(job.status)}>
            {job.status}
          </span>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Configuration & Progress */}
        <div className="lg:col-span-2 space-y-6">
          {/* Site Configuration */}
          <div className="glass-card p-6 space-y-6">
            <h2 className="text-lg font-semibold text-[rgb(var(--text-primary))]">
              Configuration
            </h2>

            <div className="flex items-center gap-4">
              {/* Source Site */}
              <div className="flex-1 p-4 rounded-xl bg-[rgba(var(--surface-0),0.5)]">
                <div className="flex items-center gap-2 text-[rgb(var(--text-muted))] mb-3">
                  <Globe className="w-4 h-4" />
                  <span className="text-sm font-medium">Source Site</span>
                </div>
                <a
                  href={job.site1_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 text-[rgb(var(--accent))] hover:underline text-sm font-mono break-all"
                >
                  {job.site1_url}
                  <ExternalLink className="w-3.5 h-3.5 flex-shrink-0" />
                </a>
                {job.site1_category && (
                  <span className="mt-2 inline-block px-2 py-1 rounded-md text-xs bg-[rgba(var(--accent),0.1)] text-[rgb(var(--accent))]">
                    {job.site1_category}
                  </span>
                )}
              </div>

              {/* Arrow */}
              <div className="p-2 rounded-full bg-[rgb(var(--surface-2))] border border-[rgba(var(--border),var(--border-opacity))]">
                <ArrowRight className="w-4 h-4 text-[rgb(var(--accent))]" />
              </div>

              {/* Target Site */}
              <div className="flex-1 p-4 rounded-xl bg-[rgba(var(--surface-0),0.5)]">
                <div className="flex items-center gap-2 text-[rgb(var(--text-muted))] mb-3">
                  <Globe className="w-4 h-4" />
                  <span className="text-sm font-medium">Target Site</span>
                </div>
                <a
                  href={job.site2_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 text-[rgb(var(--accent))] hover:underline text-sm font-mono break-all"
                >
                  {job.site2_url}
                  <ExternalLink className="w-3.5 h-3.5 flex-shrink-0" />
                </a>
                {job.site2_category && (
                  <span className="mt-2 inline-block px-2 py-1 rounded-md text-xs bg-[rgba(var(--accent),0.1)] text-[rgb(var(--accent))]">
                    {job.site2_category}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* CSV Upload Section (if pending) */}
          {job.status === 'pending' && (
            <div className="glass-card p-6 space-y-6">
              <div>
                <h2 className="text-lg font-semibold text-[rgb(var(--text-primary))] mb-2">
                  Upload Product Data
                </h2>
                <p className="text-sm text-[rgb(var(--text-muted))]">
                  Upload CSV files containing product URLs for both sites. The system will crawl each URL to extract product data for matching.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Site A (Source) Upload */}
                <CSVUploader
                  jobId={jobId}
                  site="site_a"
                  label="Source Products (Site A)"
                  description="Upload your products that need to be matched"
                  onUploadComplete={(result) => {
                    console.log('Site A upload complete:', result);
                    fetchJobData();
                  }}
                />

                {/* Site B (Target) Upload */}
                <CSVUploader
                  jobId={jobId}
                  site="site_b"
                  label="Target Catalog (Site B)"
                  description="Upload competitor products to match against"
                  onUploadComplete={(result) => {
                    console.log('Site B upload complete:', result);
                    fetchJobData();
                  }}
                />
              </div>
            </div>
          )}

          {/* Progress (if running) */}
          {job.status === 'running' && (
            <div className="glass-card p-6">
              <h2 className="text-lg font-semibold text-[rgb(var(--text-primary))] mb-4">
                Progress
              </h2>
              <ProgressBar
                progress={job.progress || 0}
                label="Processing..."
              />
            </div>
          )}
        </div>

        {/* Right Column - Stats & Actions */}
        <div className="space-y-6">
          {/* Statistics */}
          <div className="glass-card p-6">
            <h2 className="text-lg font-semibold text-[rgb(var(--text-primary))] mb-4">
              Statistics
            </h2>

            <div>
              <StatItem icon={Package} label="Total Products" value={job.total_products || 0} />
              <StatItem icon={GitCompareArrows} label="Matched Products" value={job.matched_products || 0} />
              <StatItem icon={Percent} label="Match Rate" value={`${matchRate}%`} />
            </div>
          </div>

          {/* Matcher Metrics */}
          <div className="glass-card p-6">
            <h2 className="text-lg font-semibold text-[rgb(var(--text-primary))] mb-4">Matcher Metrics</h2>
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-[rgb(var(--text-muted))]">Brand alias hits</span>
                <span className="font-mono">{metrics.alias_hits ?? 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[rgb(var(--text-muted))]">Category synonym hits</span>
                <span className="font-mono">{metrics.synonym_hits ?? 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[rgb(var(--text-muted))]">Variant hits</span>
                <span className="font-mono">{metrics.variant_hits ?? 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[rgb(var(--text-muted))]">Image OCR comparisons</span>
                <span className="font-mono">{metrics.image_comparisons ?? 0}</span>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="glass-card p-6">
            <h2 className="text-lg font-semibold text-[rgb(var(--text-primary))] mb-4">
              Actions
            </h2>

            <div className="space-y-3">
              {job.status === 'pending' && (
                <button
                  onClick={handleRunJob}
                  disabled={refreshing}
                  className="btn-primary w-full flex items-center justify-center gap-2"
                >
                  <Play className="w-4 h-4" />
                  Run Job
                </button>
              )}

              <button
                onClick={handleRefresh}
                disabled={refreshing}
                className="btn-secondary w-full flex items-center justify-center gap-2"
              >
                <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
                Refresh
              </button>

              <a
                href={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/jobs/${jobId}/export`}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary w-full flex items-center justify-center gap-2"
              >
                {/* Using a simple label to avoid extra icon import churn */}
                Export CSV
              </a>

              <a
                href={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/jobs/${jobId}/diagnostics?sample_size=50`}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary w-full flex items-center justify-center gap-2"
              >
                Diagnostics CSV
              </a>

              <button
                onClick={async () => {
                  try {
                    const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
                    const res = await fetch(`${base}/api/jobs/${jobId}`, {
                      method: 'PUT',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({
                        config: {
                          ai_validation_enabled: true,
                          ai_validation_min: 0.70,
                          ai_validation_max: 0.90,
                          ai_validation_cap: 100,
                        },
                      }),
                    });
                    if (!res.ok) throw new Error('HTTP ' + res.status);
                    alert('AI Validation enabled for this job');
                  } catch (e) {
                    alert('Failed to enable AI Validation');
                  }
                }}
                className="btn-secondary w-full flex items-center justify-center gap-2"
              >
                Enable AI Validation
              </button>

              <button
                onClick={handleDeleteJob}
                className="btn-danger w-full flex items-center justify-center gap-2"
              >
                <Trash2 className="w-4 h-4" />
                Delete Job
              </button>
            </div>
          </div>

          {/* AI Validation Settings */}
          <div className="glass-card p-6">
            <div className="flex items-center gap-2 mb-4">
              <Settings className="w-4 h-4 text-[rgb(var(--accent))]" />
              <h2 className="text-lg font-semibold text-[rgb(var(--text-primary))]">AI Validation</h2>
            </div>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-[rgb(var(--text-secondary))]">Enable AI validation</span>
                <input type="checkbox" checked={aiEnabled} onChange={(e) => setAiEnabled(e.target.checked)} />
              </div>
              {aiEnabled && (
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs text-[rgb(var(--text-muted))]">Min</label>
                    <input type="number" min={0} max={1} step={0.01} value={aiMin}
                      onChange={(e) => setAiMin(parseFloat(e.target.value || '0'))} className="input-field" />
                  </div>
                  <div>
                    <label className="block text-xs text-[rgb(var(--text-muted))]">Max</label>
                    <input type="number" min={0} max={1} step={0.01} value={aiMax}
                      onChange={(e) => setAiMax(parseFloat(e.target.value || '0'))} className="input-field" />
                  </div>
                  <div>
                    <label className="block text-xs text-[rgb(var(--text-muted))]">Cap</label>
                    <input type="number" min={0} step={1} value={aiCap}
                      onChange={(e) => setAiCap(parseInt(e.target.value || '0', 10))} className="input-field" />
                  </div>
                </div>
              )}
              <button
                onClick={async () => {
                  try {
                    await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/jobs/${jobId}`, {
                      method: 'PUT',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({
                        config: {
                          ai_validation_enabled: aiEnabled,
                          ai_validation_min: aiMin,
                          ai_validation_max: aiMax,
                          ai_validation_cap: aiCap,
                        },
                      }),
                    });
                    alert('AI settings saved');
                  } catch (e) {
                    alert('Failed to save AI settings');
                  }
                }}
                className="btn-primary w-full"
              >
                Save AI Settings
              </button>
            </div>
          </div>

          {/* Text Matching Settings */}
          <div className="glass-card p-6">
            <div className="mb-4 text-lg font-semibold text-[rgb(var(--text-primary))]">Text Matching</div>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-[rgb(var(--text-secondary))]">Embed Enriched Text</span>
                <input type="checkbox" checked={embedEnriched} onChange={(e) => setEmbedEnriched(e.target.checked)} />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-[rgb(var(--text-secondary))]">Improved Token Normalization (v2)</span>
                <input type="checkbox" checked={tokenNormV2} onChange={(e) => setTokenNormV2(e.target.checked)} />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-[rgb(var(--text-secondary))]">Use Brand Ontology</span>
                <input type="checkbox" checked={useBrandOnto} onChange={(e) => setUseBrandOnto(e.target.checked)} />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-[rgb(var(--text-secondary))]">Use Category Ontology</span>
                <input type="checkbox" checked={useCategoryOnto} onChange={(e) => setUseCategoryOnto(e.target.checked)} />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-[rgb(var(--text-secondary))]">Variant Extractor (size/shade/model)</span>
                <input type="checkbox" checked={useVariant} onChange={(e) => setUseVariant(e.target.checked)} />
              </div>
              <button
                onClick={async () => {
                  try {
                    await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/jobs/${jobId}`, {
                      method: 'PUT',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({
                        config: {
                          embed_enriched_text: embedEnriched,
                          token_norm_v2: tokenNormV2,
                          use_brand_ontology: useBrandOnto,
                          use_category_ontology: useCategoryOnto,
                          use_variant_extractor: useVariant,
                        },
                      }),
                    });
                    alert('Text matching settings saved');
                  } catch (e) {
                    alert('Failed to save settings');
                  }
                }}
                className="btn-primary w-full"
              >
                Save Text Settings
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Quick Match (No Persistence) */}
      <div className="glass-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Wand2 className="w-4 h-4 text-[rgb(var(--accent))]" />
          <h2 className="text-lg font-semibold text-[rgb(var(--text-primary))]">Quick Match (No Persistence)</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <input className="input-field md:col-span-2" placeholder="Title (required)" value={qmTitle} onChange={(e) => setQmTitle(e.target.value)} />
          <input className="input-field" placeholder="Brand" value={qmBrand} onChange={(e) => setQmBrand(e.target.value)} />
          <input className="input-field" placeholder="Category" value={qmCategory} onChange={(e) => setQmCategory(e.target.value)} />
          <input className="input-field" placeholder="Price" value={qmPrice} onChange={(e) => setQmPrice(e.target.value)} />
          <input className="input-field md:col-span-5" placeholder="URL (optional)" value={qmUrl} onChange={(e) => setQmUrl(e.target.value)} />
        </div>
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={async () => {
              if (!qmTitle) return alert('Title is required');
              setQmLoading(true);
              setQmResults(null);
              try {
                const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
                const resp = await fetch(`${base}/api/match/quick`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    job_id: jobId,
                    title: qmTitle,
                    url: qmUrl || undefined,
                    brand: qmBrand || undefined,
                    category: qmCategory || undefined,
                    price: qmPrice ? parseFloat(qmPrice) : undefined,
                  })
                });
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                const data = await resp.json();
                setQmResults(data);
              } catch (e) {
                alert('Quick match failed');
              } finally {
                setQmLoading(false);
              }
            }}
            className="btn-secondary"
          >
            {qmLoading ? 'Matching…' : 'Run Quick Match'}
          </button>
          <button onClick={() => { setQmResults(null); }} className="btn-secondary">Clear</button>
        </div>
        {qmResults && (
          <div className="mt-4">
            {qmResults.best_match && (
              <div className="mb-3 p-3 rounded border border-[rgba(var(--border),var(--border-opacity))]">
                <div className="text-sm text-[rgb(var(--text-muted))] mb-1">Best Match</div>
                <div className="font-medium">{qmResults.best_match.title}</div>
                <div className="text-xs">Score: {(qmResults.best_match.score * 100).toFixed(1)}% • Tier: {qmResults.best_match.confidence_tier}</div>
                <a href={qmResults.best_match.url} target="_blank" className="text-xs text-[rgb(var(--accent))]">{qmResults.best_match.url}</a>
              </div>
            )}
            <div className="text-sm text-[rgb(var(--text-secondary))] mb-2">Top 5 Candidates</div>
            <div className="space-y-2">
              {qmResults.top_5?.map((c: any) => (
                <div key={c.product_id} className="p-3 rounded bg-[rgba(var(--surface-0),0.5)] border border-[rgba(var(--border),var(--border-opacity))]">
                  <div className="font-medium">{c.title}</div>
                  <div className="text-xs">Score: {(c.score * 100).toFixed(1)}% • Tier: {c.confidence_tier}</div>
                  <a href={c.url} target="_blank" className="text-xs text-[rgb(var(--accent))]">{c.url}</a>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Matches Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold text-[rgb(var(--text-primary))]">
            Matches
            <span className="ml-2 text-[rgb(var(--text-muted))] font-normal">({matches.length})</span>
          </h2>
        </div>
        <MatchTable
          matches={matches}
          onApprove={handleApproveMatch}
          onReject={handleRejectMatch}
        />
      </div>
    </div>
  );
}
