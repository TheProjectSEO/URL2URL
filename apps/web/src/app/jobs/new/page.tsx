'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Loader2, Globe, ArrowRight, Lightbulb, Sparkles } from 'lucide-react';
import Link from 'next/link';
import { api, type CreateJobRequest } from '@/lib/api';

export default function NewJobPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formData, setFormData] = useState<CreateJobRequest>({
    name: '',
    site1_url: '',
    site2_url: '',
    site1_category: '',
    site2_category: '',
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

      router.push(`/jobs/${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create job');
      setLoading(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

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
            Create New Job
          </h1>
          <p className="text-[rgb(var(--text-secondary))]">
            Set up a new product matching job between two e-commerce websites
          </p>
        </div>
      </div>

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
                  <span className="text-sm font-medium">Source Site</span>
                </div>
                <div className="space-y-2">
                  <label htmlFor="site1_url" className="block text-sm font-medium text-[rgb(var(--text-primary))]">
                    URL
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
                    placeholder="https://nykaa.com/lipsticks"
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
                  <span className="text-sm font-medium">Target Site</span>
                </div>
                <div className="space-y-2">
                  <label htmlFor="site2_url" className="block text-sm font-medium text-[rgb(var(--text-primary))]">
                    URL
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
                    placeholder="https://purplle.com/lipsticks"
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
                  Create Job
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
                  Use category or collection pages for better product coverage
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-[rgb(var(--accent))]">•</span>
                  Ensure both sites sell similar product types
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-[rgb(var(--accent))]">•</span>
                  Specify categories to improve matching accuracy
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-[rgb(var(--accent))]">•</span>
                  Jobs start in pending status — run manually or wait for auto-start
                </li>
              </ul>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
