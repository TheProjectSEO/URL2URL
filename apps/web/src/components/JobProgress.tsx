'use client';

import { useState, useEffect, useCallback } from 'react';
import { Loader2, CheckCircle2, Clock, AlertCircle } from 'lucide-react';

interface ProgressData {
  stage: string;
  current: number;
  total: number;
  rate: number;
  eta_seconds: number;
  message: string;
}

interface JobProgressProps {
  jobId: string;
  onComplete?: () => void;
  apiBase?: string;
}

type Counters = {
  processed: number;
  matched: number;
  high_confidence: number;
  no_match: number;
  needs_review: number;
  embedding_failed: number;
  image_text_comparisons?: number;
};

function parseMessage(raw: string): { text: string; counters?: Counters } {
  if (!raw) return { text: '' };
  try {
    const obj = JSON.parse(raw);
    if (obj && typeof obj === 'object') {
      return { text: obj.text || '', counters: obj.counters };
    }
  } catch (_) {
    // fall through if not JSON
  }
  return { text: raw };
}

const STAGE_LABELS: Record<string, { label: string; icon: string }> = {
  pending: { label: 'Pending', icon: '⏳' },
  crawling_site_a: { label: 'Crawling Site A Products', icon: '🔍' },
  crawling_site_b: { label: 'Crawling Site B Products', icon: '🔍' },
  generating_embeddings: { label: 'Generating Embeddings', icon: '🧠' },
  matching: { label: 'Matching Products', icon: '🔗' },
  completed: { label: 'Completed', icon: '✅' },
  failed: { label: 'Failed', icon: '❌' },
  running: { label: 'Running', icon: '⚡' },
};

export function JobProgress({ jobId, onComplete, apiBase = '' }: JobProgressProps) {
  const [progress, setProgress] = useState<ProgressData | null>(null);
  const [isPolling, setIsPolling] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProgress = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/jobs/${jobId}/progress`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setProgress(data);
      setError(null);
      if (data.stage === 'completed') { setIsPolling(false); onComplete?.(); }
      else if (data.stage === 'failed') { setIsPolling(false); }
    } catch (e) {
      console.error('Progress poll failed:', e);
      setError('Failed to fetch progress');
    }
  }, [jobId, apiBase, onComplete]);

  useEffect(() => {
    if (!isPolling) return;
    fetchProgress();
    const interval = setInterval(fetchProgress, 4000);
    return () => clearInterval(interval);
  }, [fetchProgress, isPolling]);

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
        <AlertCircle className="w-5 h-5 text-red-500" />
        <span className="text-red-700">{error}</span>
      </div>
    );
  }

  if (!progress) {
    return (
      <div className="bg-gray-50 rounded-lg p-6 animate-pulse">
        <div className="h-4 bg-gray-200 rounded w-1/3 mb-4"></div>
        <div className="h-2 bg-gray-200 rounded w-full mb-2"></div>
        <div className="h-3 bg-gray-200 rounded w-1/4"></div>
      </div>
    );
  }

  const stageInfo = STAGE_LABELS[progress.stage] || { label: progress.stage, icon: '⏳' };
  const parsed = parseMessage(progress.message);
  const percentage = progress.total > 0 ? (progress.current / progress.total) * 100 : 0;
  const isComplete = progress.stage === 'completed';
  const isFailed = progress.stage === 'failed';

  const formatETA = (seconds: number): string => {
    if (seconds <= 0) return 'Calculating...';
    if (seconds < 60) return `${seconds}s remaining`;
    const minutes = Math.ceil(seconds / 60);
    return `~${minutes} min remaining`;
  };

  return (
    <div className={`rounded-lg p-6 space-y-4 ${
      isComplete ? 'bg-green-50 border border-green-200' :
      isFailed ? 'bg-red-50 border border-red-200' :
      'bg-white border border-gray-200 shadow-sm'
    }`}>
      <div className="flex items-center gap-3">
        <span className="text-2xl">{stageInfo.icon}</span>
        <div className="flex-1">
          <h3 className="font-semibold text-gray-900">{stageInfo.label}</h3>
          <p className="text-sm text-gray-500">{parsed.text}</p>
        </div>
        {!isComplete && !isFailed && (<Loader2 className="w-5 h-5 animate-spin text-blue-500" />)}
        {isComplete && (<CheckCircle2 className="w-5 h-5 text-green-500" />)}
      </div>

      {!isComplete && !isFailed && (
        <div className="relative h-3 bg-gray-200 rounded-full overflow-hidden">
          <div className="absolute h-full bg-gradient-to-r from-blue-500 to-blue-400 transition-all duration-500 ease-out" style={{ width: `${percentage}%` }} />
        </div>
      )}

      <div className="flex justify-between text-sm text-gray-600">
        <span className="font-mono">{progress.current.toLocaleString()} / {progress.total.toLocaleString()}</span>
        {!isComplete && !isFailed && progress.total > 0 && (
          <span className="flex items-center gap-1"><Clock className="w-4 h-4" />{formatETA(progress.eta_seconds)}</span>
        )}
        {progress.rate > 0 && (<span className="text-gray-400">{progress.rate.toFixed(1)}/s</span>)}
      </div>

      {parsed.counters && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs text-gray-700">
          <div className="bg-gray-50 border border-gray-200 rounded px-2 py-1">Processed: <span className="font-mono">{parsed.counters.processed}</span></div>
          <div className="bg-green-50 border border-green-200 rounded px-2 py-1">Matched: <span className="font-mono">{parsed.counters.matched}</span></div>
          <div className="bg-blue-50 border border-blue-200 rounded px-2 py-1">High Conf: <span className="font-mono">{parsed.counters.high_confidence}</span></div>
          <div className="bg-yellow-50 border border-yellow-200 rounded px-2 py-1">Needs Review: <span className="font-mono">{parsed.counters.needs_review}</span></div>
          <div className="bg-red-50 border border-red-200 rounded px-2 py-1">No Match: <span className="font-mono">{parsed.counters.no_match}</span></div>
          <div className="bg-gray-50 border border-gray-200 rounded px-2 py-1">Emb Fail: <span className="font-mono">{parsed.counters.embedding_failed}</span></div>
        </div>
      )}
    </div>
  );
}

export default JobProgress;
