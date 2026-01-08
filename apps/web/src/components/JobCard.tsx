'use client';

import Link from 'next/link';
import { Clock, ArrowRight, Trash2, Play, Globe, Package, GitCompareArrows } from 'lucide-react';
import { formatRelativeTime } from '@/lib/utils';
import type { Job } from '@/lib/api';
import ProgressBar from './ProgressBar';

interface JobCardProps {
  job: Job;
  onDelete?: (id: string) => void;
  onRun?: (id: string) => void;
}

// Safely extract hostname from URL
function safeHostname(url: string | undefined | null): string {
  if (!url) return 'Unknown';
  try {
    return new URL(url).hostname.replace('www.', '');
  } catch {
    return url;
  }
}

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

export default function JobCard({ job, onDelete, onRun }: JobCardProps) {
  const handleDelete = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (confirm('Are you sure you want to delete this job?')) {
      onDelete?.(job.id);
    }
  };

  const handleRun = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onRun?.(job.id);
  };

  return (
    <Link href={`/jobs/${job.id}`} className="block group">
      <div className="glass-card p-5 transition-all duration-300 hover:border-[rgba(var(--accent),0.3)] hover:shadow-[0_0_30px_-5px_rgba(var(--accent),0.15)]">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-medium text-[rgb(var(--text-primary))] truncate group-hover:text-[rgb(var(--accent))] transition-colors">
              {job.name}
            </h3>
            <div className="flex items-center gap-2 mt-1.5 text-sm text-[rgb(var(--text-muted))]">
              <Clock className="w-3.5 h-3.5" />
              <span>{formatRelativeTime(job.created_at)}</span>
            </div>
          </div>
          <span className={getStatusBadgeClass(job.status)}>
            {job.status}
          </span>
        </div>

        {/* Sites */}
        <div className="flex items-center gap-3 p-3 rounded-lg bg-[rgba(var(--surface-0),0.5)] mb-4">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <Globe className="w-4 h-4 text-[rgb(var(--text-muted))] flex-shrink-0" />
            <span className="font-mono text-sm text-[rgb(var(--text-secondary))] truncate">
              {safeHostname(job.site1_url)}
            </span>
          </div>
          <ArrowRight className="w-4 h-4 text-[rgb(var(--accent))] flex-shrink-0" />
          <div className="flex items-center gap-2 flex-1 min-w-0 justify-end">
            <span className="font-mono text-sm text-[rgb(var(--text-secondary))] truncate">
              {safeHostname(job.site2_url)}
            </span>
            <Globe className="w-4 h-4 text-[rgb(var(--text-muted))] flex-shrink-0" />
          </div>
        </div>

        {/* Categories */}
        {(job.site1_category || job.site2_category) && (
          <div className="flex flex-wrap gap-2 mb-4">
            {job.site1_category && (
              <span className="px-2 py-1 text-xs font-medium rounded-md bg-[rgba(var(--accent),0.1)] text-[rgb(var(--accent))]">
                {job.site1_category}
              </span>
            )}
            {job.site2_category && (
              <span className="px-2 py-1 text-xs font-medium rounded-md bg-[rgba(var(--accent),0.1)] text-[rgb(var(--accent))]">
                {job.site2_category}
              </span>
            )}
          </div>
        )}

        {/* Progress or Stats */}
        {job.status === 'running' ? (
          <ProgressBar progress={job.progress || 0} />
        ) : (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4 text-sm">
              {job.total_products !== undefined && job.total_products > 0 && (
                <div className="flex items-center gap-1.5 text-[rgb(var(--text-muted))]">
                  <Package className="w-3.5 h-3.5" />
                  <span>{job.total_products.toLocaleString()} products</span>
                </div>
              )}
              {job.matched_products !== undefined && job.matched_products > 0 && (
                <div className="flex items-center gap-1.5 text-[rgb(var(--text-muted))]">
                  <GitCompareArrows className="w-3.5 h-3.5" />
                  <span>{job.matched_products.toLocaleString()} matches</span>
                </div>
              )}
            </div>

            <div className="flex items-center gap-1">
              {job.status === 'pending' && onRun && (
                <button
                  onClick={handleRun}
                  className="p-2 rounded-lg text-[rgb(var(--accent))] hover:bg-[rgba(var(--accent),0.1)] transition-colors"
                  title="Run job"
                >
                  <Play className="w-4 h-4" />
                </button>
              )}
              {onDelete && (
                <button
                  onClick={handleDelete}
                  className="p-2 rounded-lg text-[rgb(var(--text-muted))] hover:text-red-400 hover:bg-red-400/10 transition-colors"
                  title="Delete job"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </Link>
  );
}
