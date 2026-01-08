'use client';

import { useState } from 'react';
import { ExternalLink, Check, X, ArrowUpDown, Filter, Search, ChevronDown, ChevronUp } from 'lucide-react';
import type { Match } from '@/lib/api';
import ConfidenceBadge from './ConfidenceBadge';

interface MatchTableProps {
  matches: Match[];
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
}

type SortField = 'score' | 'confidence_tier' | 'status';
type SortDirection = 'asc' | 'desc';

// Get status badge class
function getStatusBadgeClass(status: string): string {
  const statusMap: Record<string, string> = {
    pending: 'badge-pending',
    approved: 'badge-completed',
    rejected: 'badge-failed',
  };
  return statusMap[status] || 'badge-pending';
}

function SortableHeader({
  label,
  field,
  currentField,
  direction,
  onSort,
}: {
  label: string;
  field: SortField;
  currentField: SortField;
  direction: SortDirection;
  onSort: (field: SortField) => void;
}) {
  const isActive = currentField === field;

  return (
    <button
      onClick={() => onSort(field)}
      className={`
        flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider
        transition-colors duration-200
        ${isActive
          ? 'text-[rgb(var(--accent))]'
          : 'text-[rgb(var(--text-muted))] hover:text-[rgb(var(--text-secondary))]'
        }
      `}
    >
      {label}
      <span className="flex flex-col -space-y-1">
        <ChevronUp className={`w-3 h-3 ${isActive && direction === 'asc' ? 'opacity-100' : 'opacity-30'}`} />
        <ChevronDown className={`w-3 h-3 ${isActive && direction === 'desc' ? 'opacity-100' : 'opacity-30'}`} />
      </span>
    </button>
  );
}

function FilterButton({
  label,
  value,
  currentFilter,
  count,
  onClick,
}: {
  label: string;
  value: string;
  currentFilter: string;
  count?: number;
  onClick: () => void;
}) {
  const isActive = currentFilter === value;

  return (
    <button
      onClick={onClick}
      className={`
        px-3 py-1.5 text-xs font-medium rounded-lg transition-all duration-200
        flex items-center gap-2
        ${isActive
          ? 'bg-[rgb(var(--accent))] text-white shadow-[0_0_12px_rgba(var(--accent),0.4)]'
          : 'bg-[rgb(var(--surface-2))] text-[rgb(var(--text-secondary))] hover:bg-[rgb(var(--surface-3))] hover:text-[rgb(var(--text-primary))]'
        }
      `}
    >
      {label}
      {count !== undefined && (
        <span className={`
          px-1.5 py-0.5 text-[10px] rounded-md
          ${isActive ? 'bg-white/20' : 'bg-[rgba(var(--accent),0.15)] text-[rgb(var(--accent))]'}
        `}>
          {count}
        </span>
      )}
    </button>
  );
}

function EmptyState() {
  return (
    <div className="glass-card p-12 text-center animate-fade-in">
      <div className="max-w-sm mx-auto space-y-4">
        <div className="p-3 rounded-xl bg-[rgba(var(--accent),0.1)] w-fit mx-auto">
          <Search className="w-6 h-6 text-[rgb(var(--accent))]" />
        </div>
        <div className="space-y-2">
          <h3 className="text-lg font-medium text-[rgb(var(--text-primary))]">
            No matches found
          </h3>
          <p className="text-sm text-[rgb(var(--text-muted))]">
            Run the job to start finding product matches between the two sites.
          </p>
        </div>
      </div>
    </div>
  );
}

function ProductCell({ title, url }: { title: string; url: string }) {
  return (
    <div className="space-y-1.5">
      <p className="text-sm font-medium text-[rgb(var(--text-primary))] line-clamp-2 leading-snug">
        {title}
      </p>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-xs text-[rgb(var(--accent))] hover:text-[rgba(var(--accent),0.8)] transition-colors group"
      >
        <span className="font-mono truncate max-w-[180px] opacity-70 group-hover:opacity-100">
          {new URL(url).hostname}
        </span>
        <ExternalLink className="w-3 h-3 flex-shrink-0" />
      </a>
    </div>
  );
}

export default function MatchTable({ matches, onApprove, onReject }: MatchTableProps) {
  const [sortField, setSortField] = useState<SortField>('score');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [filter, setFilter] = useState<string>('all');

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const filteredMatches = matches.filter((match) => {
    if (filter === 'all') return true;
    return match.status === filter;
  });

  const sortedMatches = [...filteredMatches].sort((a, b) => {
    let comparison = 0;

    if (sortField === 'score') {
      comparison = a.score - b.score;
    } else if (sortField === 'confidence_tier') {
      const tierOrder = ['exact_match', 'high_confidence', 'good_match', 'likely_match', 'manual_review', 'no_match'];
      comparison = tierOrder.indexOf(a.confidence_tier) - tierOrder.indexOf(b.confidence_tier);
    } else if (sortField === 'status') {
      comparison = a.status.localeCompare(b.status);
    }

    return sortDirection === 'asc' ? comparison : -comparison;
  });

  // Calculate counts for filter badges
  const counts = {
    all: matches.length,
    pending: matches.filter(m => m.status === 'pending').length,
    approved: matches.filter(m => m.status === 'approved').length,
    rejected: matches.filter(m => m.status === 'rejected').length,
  };

  if (matches.length === 0) {
    return <EmptyState />;
  }

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Filter Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 glass-card">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-[rgb(var(--text-muted))]">
            <Filter className="w-4 h-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Filter</span>
          </div>
          <div className="flex gap-2">
            <FilterButton
              label="All"
              value="all"
              currentFilter={filter}
              count={counts.all}
              onClick={() => setFilter('all')}
            />
            <FilterButton
              label="Pending"
              value="pending"
              currentFilter={filter}
              count={counts.pending}
              onClick={() => setFilter('pending')}
            />
            <FilterButton
              label="Approved"
              value="approved"
              currentFilter={filter}
              count={counts.approved}
              onClick={() => setFilter('approved')}
            />
            <FilterButton
              label="Rejected"
              value="rejected"
              currentFilter={filter}
              count={counts.rejected}
              onClick={() => setFilter('rejected')}
            />
          </div>
        </div>

        <div className="text-xs text-[rgb(var(--text-muted))] font-mono">
          Showing <span className="text-[rgb(var(--accent))]">{sortedMatches.length}</span> of {matches.length} matches
        </div>
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[rgba(var(--border),var(--border-opacity))]">
                <th className="px-6 py-4 text-left text-xs font-medium text-[rgb(var(--text-muted))] uppercase tracking-wider">
                  Source Product
                </th>
                <th className="px-6 py-4 text-left text-xs font-medium text-[rgb(var(--text-muted))] uppercase tracking-wider">
                  Matched Product
                </th>
                <th className="px-6 py-4 text-left">
                  <SortableHeader
                    label="Score"
                    field="score"
                    currentField={sortField}
                    direction={sortDirection}
                    onSort={handleSort}
                  />
                </th>
                <th className="px-6 py-4 text-left">
                  <SortableHeader
                    label="Confidence"
                    field="confidence_tier"
                    currentField={sortField}
                    direction={sortDirection}
                    onSort={handleSort}
                  />
                </th>
                <th className="px-6 py-4 text-left">
                  <SortableHeader
                    label="Status"
                    field="status"
                    currentField={sortField}
                    direction={sortDirection}
                    onSort={handleSort}
                  />
                </th>
                <th className="px-6 py-4 text-right text-xs font-medium text-[rgb(var(--text-muted))] uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[rgba(var(--border),var(--border-opacity))]">
              {sortedMatches.map((match, index) => (
                <tr
                  key={match.id}
                  className="group transition-colors hover:bg-[rgba(var(--accent),0.03)] animate-fade-in"
                  style={{ animationDelay: `${index * 20}ms` }}
                >
                  <td className="px-6 py-4">
                    <ProductCell title={match.source_title} url={match.source_url} />
                  </td>
                  <td className="px-6 py-4">
                    <ProductCell title={match.matched_title} url={match.matched_url} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1.5 rounded-full bg-[rgb(var(--surface-3))] overflow-hidden">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-[rgb(var(--accent))] to-[rgba(var(--accent),0.6)] transition-all duration-500"
                          style={{ width: `${Math.round(match.score * 100)}%` }}
                        />
                      </div>
                      <span className="text-sm font-mono font-medium text-[rgb(var(--text-primary))]">
                        {Math.round(match.score * 100)}%
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <ConfidenceBadge tier={match.confidence_tier} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={getStatusBadgeClass(match.status)}>
                      {match.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    {match.status === 'pending' && (
                      <div className="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                        {onApprove && (
                          <button
                            onClick={() => onApprove(match.id)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg
                              bg-emerald-500/10 text-emerald-400 border border-emerald-500/20
                              hover:bg-emerald-500/20 hover:border-emerald-500/30
                              transition-all duration-200"
                          >
                            <Check className="w-3.5 h-3.5" />
                            Approve
                          </button>
                        )}
                        {onReject && (
                          <button
                            onClick={() => onReject(match.id)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg
                              bg-red-500/10 text-red-400 border border-red-500/20
                              hover:bg-red-500/20 hover:border-red-500/30
                              transition-all duration-200"
                          >
                            <X className="w-3.5 h-3.5" />
                            Reject
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
