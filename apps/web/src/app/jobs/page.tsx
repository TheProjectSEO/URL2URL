'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Plus, Filter } from 'lucide-react';
import { api, type Job } from '@/lib/api';
import JobCard from '@/components/JobCard';
import { LoadingPage } from '@/components/LoadingSpinner';

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [filteredJobs, setFilteredJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('all');

  useEffect(() => {
    fetchJobs();
  }, []);

  useEffect(() => {
    if (filter === 'all') {
      setFilteredJobs(jobs);
    } else {
      setFilteredJobs(jobs.filter(job => job.status === filter));
    }
  }, [filter, jobs]);

  const fetchJobs = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.jobs.list();
      setJobs(data);
      setFilteredJobs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load jobs');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteJob = async (id: string) => {
    try {
      await api.jobs.delete(id);
      setJobs(jobs.filter(job => job.id !== id));
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete job');
    }
  };

  const handleRunJob = async (id: string) => {
    try {
      await api.jobs.run(id);
      fetchJobs();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to start job');
    }
  };

  if (loading) return <LoadingPage />;

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-600 dark:text-red-400 mb-4">Error: {error}</p>
        <button
          onClick={fetchJobs}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            Jobs
          </h1>
          <p className="mt-2 text-gray-600 dark:text-gray-400">
            Manage all your product matching jobs
          </p>
        </div>
        <Link
          href="/jobs/new"
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-5 h-5" />
          New Job
        </Link>
      </div>

      <div className="flex items-center gap-4">
        <Filter className="w-5 h-5 text-gray-500 dark:text-gray-400" />
        <div className="flex gap-2">
          {['all', 'pending', 'crawling', 'matching', 'completed', 'failed'].map((status) => (
            <button
              key={status}
              onClick={() => setFilter(status)}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                filter === status
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
              }`}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </button>
          ))}
        </div>
        <span className="ml-auto text-sm text-gray-500 dark:text-gray-400">
          Showing {filteredJobs.length} of {jobs.length} jobs
        </span>
      </div>

      {filteredJobs.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-12 text-center">
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            {filter === 'all'
              ? 'No jobs yet. Create your first matching job to get started.'
              : `No ${filter} jobs found.`}
          </p>
          {filter === 'all' && (
            <Link
              href="/jobs/new"
              className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
            >
              <Plus className="w-5 h-5" />
              Create Job
            </Link>
          )}
        </div>
      ) : (
        <div className="grid gap-4 grid-cols-1 lg:grid-cols-2 xl:grid-cols-3">
          {filteredJobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              onDelete={handleDeleteJob}
              onRun={handleRunJob}
            />
          ))}
        </div>
      )}
    </div>
  );
}
