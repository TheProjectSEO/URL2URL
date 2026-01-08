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
  Loader2
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
      setMatches(matchesData);
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

              <button
                onClick={handleDeleteJob}
                className="btn-danger w-full flex items-center justify-center gap-2"
              >
                <Trash2 className="w-4 h-4" />
                Delete Job
              </button>
            </div>
          </div>
        </div>
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
