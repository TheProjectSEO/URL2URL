'use client';

import { useState, useCallback, useRef } from 'react';
import { Upload, FileText, CheckCircle2, AlertCircle, X, Download } from 'lucide-react';
import { api, CSVUploadResponse } from '@/lib/api';

interface CSVUploaderProps {
  jobId: string;
  site: 'site_a' | 'site_b';
  label: string;
  description: string;
  onUploadComplete?: (result: CSVUploadResponse) => void;
}

export function CSVUploader({ jobId, site, label, description, onUploadComplete }: CSVUploaderProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<CSVUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = useCallback((selectedFile: File) => {
    if (!selectedFile.name.endsWith('.csv')) {
      setError('Please select a CSV file');
      return;
    }
    setFile(selectedFile);
    setError(null);
    setResult(null);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      handleFileSelect(droppedFile);
    }
  }, [handleFileSelect]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setError(null);

    try {
      const uploadResult = await api.upload.csv(jobId, site, file);
      setResult(uploadResult);
      onUploadComplete?.(uploadResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const clearFile = () => {
    setFile(null);
    setResult(null);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const downloadTemplate = () => {
    const csvContent = 'url,title,brand,category,price\nhttps://example.com/product/1,Example Product,Brand Name,Category,99.99';
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'product_template.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-[rgb(var(--text-primary))]">{label}</h3>
          <p className="text-xs text-[rgb(var(--text-muted))]">{description}</p>
        </div>
        <button
          onClick={downloadTemplate}
          className="text-xs text-[rgb(var(--accent))] hover:underline flex items-center gap-1"
        >
          <Download className="w-3 h-3" />
          Download Template
        </button>
      </div>

      {/* Drop Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
        className={`
          relative border-2 border-dashed rounded-lg p-6 text-center cursor-pointer
          transition-all duration-200
          ${dragOver
            ? 'border-[rgb(var(--accent))] bg-[rgba(var(--accent),0.1)]'
            : 'border-[rgba(var(--border),var(--border-opacity))] hover:border-[rgb(var(--accent))]'
          }
          ${file ? 'bg-[rgba(var(--surface-0),0.5)]' : ''}
        `}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
          className="hidden"
        />

        {file ? (
          <div className="flex items-center justify-center gap-3">
            <FileText className="w-8 h-8 text-[rgb(var(--accent))]" />
            <div className="text-left">
              <p className="text-sm font-medium text-[rgb(var(--text-primary))]">{file.name}</p>
              <p className="text-xs text-[rgb(var(--text-muted))]">
                {(file.size / 1024).toFixed(1)} KB
              </p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                clearFile();
              }}
              className="p-1 rounded hover:bg-[rgba(var(--border),0.3)]"
            >
              <X className="w-4 h-4 text-[rgb(var(--text-muted))]" />
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            <Upload className="w-8 h-8 mx-auto text-[rgb(var(--text-muted))]" />
            <p className="text-sm text-[rgb(var(--text-secondary))]">
              Drop CSV file here or <span className="text-[rgb(var(--accent))]">browse</span>
            </p>
            <p className="text-xs text-[rgb(var(--text-muted))]">
              Required: url column. Optional: title, brand, category, price
            </p>
          </div>
        )}
      </div>

      {/* Error Message */}
      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20">
          <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {/* Success Result */}
      {result && (
        <div className="p-4 rounded-lg bg-[rgba(var(--accent),0.1)] border border-[rgba(var(--accent),0.2)]">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle2 className="w-5 h-5 text-green-400" />
            <span className="text-sm font-medium text-[rgb(var(--text-primary))]">
              Upload Complete
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <span className="text-[rgb(var(--text-muted))]">Uploaded:</span>{' '}
              <span className="text-green-400 font-mono">{result.uploaded}</span>
            </div>
            <div>
              <span className="text-[rgb(var(--text-muted))]">Failed:</span>{' '}
              <span className={result.failed > 0 ? 'text-red-400 font-mono' : 'text-[rgb(var(--text-muted))] font-mono'}>
                {result.failed}
              </span>
            </div>
          </div>
          {result.errors.length > 0 && (
            <div className="mt-2 pt-2 border-t border-[rgba(var(--border),var(--border-opacity))]">
              <p className="text-xs text-[rgb(var(--text-muted))] mb-1">Errors:</p>
              <ul className="text-xs text-red-400 space-y-0.5">
                {result.errors.slice(0, 3).map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
                {result.errors.length > 3 && (
                  <li>...and {result.errors.length - 3} more</li>
                )}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Upload Button */}
      {file && !result && (
        <button
          onClick={handleUpload}
          disabled={uploading}
          className="w-full btn-primary flex items-center justify-center gap-2"
        >
          {uploading ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Uploading...
            </>
          ) : (
            <>
              <Upload className="w-4 h-4" />
              Upload {site === 'site_a' ? 'Source' : 'Target'} Products
            </>
          )}
        </button>
      )}
    </div>
  );
}
