'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Plus, TrendingUp, CheckCircle, Clock, Zap, ArrowRight, BarChart3, Loader2 } from 'lucide-react';
import { api, type Job, type JobStats } from '@/lib/api';
import JobCard from '@/components/JobCard';

function StatCard({
  label,
  value,
  icon: Icon,
  accent = 'violet',
  delay = 0
}: {
  label: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
  accent?: 'violet' | 'amber' | 'emerald' | 'blue';
  delay?: number;
}) {
  const accentColors = {
    violet: 'from-violet-500/20 to-violet-500/5 text-violet-400',
    amber: 'from-amber-500/20 to-amber-500/5 text-amber-400',
    emerald: 'from-emerald-500/20 to-emerald-500/5 text-emerald-400',
    blue: 'from-blue-500/20 to-blue-500/5 text-blue-400',
  };

  return (
    <div
      className="stat-card animate-fade-in"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <p className="text-sm font-medium text-[rgb(var(--text-muted))]">
            {label}
          </p>
          <p className="text-3xl font-semibold tracking-tight text-[rgb(var(--text-primary))]">
            {value.toLocaleString()}
          </p>
        </div>
        <div className={`p-3 rounded-xl bg-gradient-to-br ${accentColors[accent]}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
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
        <p className="text-[rgb(var(--text-muted))] text-sm">Loading dashboard...</p>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="glass-card p-12 text-center animate-fade-in">
      <div className="max-w-md mx-auto space-y-6">
        <div className="relative inline-block">
          <div className="absolute inset-0 bg-[rgb(var(--accent))] blur-2xl opacity-30" />
          <div className="relative p-4 rounded-2xl bg-gradient-to-br from-[rgb(var(--accent))] to-[rgba(var(--accent),0.6)]">
            <Zap className="w-8 h-8 text-white" />
          </div>
        </div>
        <div className="space-y-2">
          <h3 className="text-xl font-semibold text-[rgb(var(--text-primary))]">
            No matching jobs yet
          </h3>
          <p className="text-[rgb(var(--text-muted))]">
            Create your first job to start matching products between e-commerce websites using AI.
          </p>
        </div>
        <Link
          href="/jobs/new"
          className="btn-primary inline-flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          Create Your First Job
        </Link>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<JobStats | null>(null);
  const [recentJobs, setRecentJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [statsData, jobsData] = await Promise.all([
        api.stats.get().catch(() => ({
          total_jobs: 0,
          active_jobs: 0,
          completed_jobs: 0,
          total_matches: 0,
          approved_matches: 0,
        })),
        api.jobs.list(),
      ]);

      setStats(statsData);
      setRecentJobs(jobsData.slice(0, 6));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteJob = async (id: string) => {
    try {
      await api.jobs.delete(id);
      setRecentJobs(recentJobs.filter(job => job.id !== id));
      if (stats) {
        setStats({
          ...stats,
          total_jobs: stats.total_jobs - 1,
        });
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete job');
    }
  };

  const handleRunJob = async (id: string) => {
    try {
      await api.jobs.run(id);
      fetchData();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to start job');
    }
  };

  if (loading) return <LoadingState />;

  if (error) {
    return (
      <div className="glass-card p-12 text-center animate-fade-in">
        <div className="max-w-md mx-auto space-y-4">
          <p className="text-red-400">{error}</p>
          <button onClick={fetchData} className="btn-primary">
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-10">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 animate-fade-in">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight text-[rgb(var(--text-primary))]">
            Dashboard
          </h1>
          <p className="text-[rgb(var(--text-secondary))]">
            AI-powered product matching across e-commerce websites
          </p>
        </div>
        <Link href="/jobs/new" className="btn-primary flex items-center gap-2 w-fit">
          <Plus className="w-4 h-4" />
          New Matching Job
        </Link>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Jobs"
          value={stats?.total_jobs || 0}
          icon={BarChart3}
          accent="violet"
          delay={0}
        />
        <StatCard
          label="Active Jobs"
          value={stats?.active_jobs || 0}
          icon={Clock}
          accent="amber"
          delay={50}
        />
        <StatCard
          label="Completed"
          value={stats?.completed_jobs || 0}
          icon={CheckCircle}
          accent="emerald"
          delay={100}
        />
        <StatCard
          label="Total Matches"
          value={stats?.total_matches || 0}
          icon={TrendingUp}
          accent="blue"
          delay={150}
        />
      </div>

      {/* Recent Jobs */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold text-[rgb(var(--text-primary))]">
            Recent Jobs
          </h2>
          {recentJobs.length > 0 && (
            <Link
              href="/jobs"
              className="nav-link flex items-center gap-1 text-sm"
            >
              View all
              <ArrowRight className="w-4 h-4" />
            </Link>
          )}
        </div>

        {recentJobs.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="grid gap-4 grid-cols-1 lg:grid-cols-2">
            {recentJobs.map((job, index) => (
              <div
                key={job.id}
                className="animate-fade-in"
                style={{ animationDelay: `${(index + 4) * 50}ms` }}
              >
                <JobCard
                  job={job}
                  onDelete={handleDeleteJob}
                  onRun={handleRunJob}
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
