'use client';

interface ConfidenceBadgeProps {
  tier: string;
  score?: number;
  showScore?: boolean;
}

// Map confidence tier to badge class
function getConfidenceBadgeClass(tier: string): string {
  const tierMap: Record<string, string> = {
    exact_match: 'badge-confidence-exact-match',
    high_confidence: 'badge-confidence-high-confidence',
    good_match: 'badge-confidence-good-match',
    likely_match: 'badge-confidence-likely-match',
    manual_review: 'badge-confidence-manual-review',
    no_match: 'badge-confidence-no-match',
  };
  return tierMap[tier] || 'badge-confidence-manual-review';
}

// Format tier name for display
function formatTierName(tier: string): string {
  return tier
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

export default function ConfidenceBadge({ tier, score, showScore = false }: ConfidenceBadgeProps) {
  return (
    <div className="flex items-center gap-2">
      <span className={getConfidenceBadgeClass(tier)}>
        {formatTierName(tier)}
      </span>
      {showScore && score !== undefined && (
        <span className="text-xs font-mono text-[rgb(var(--text-muted))]">
          {Math.round(score * 100)}%
        </span>
      )}
    </div>
  );
}
