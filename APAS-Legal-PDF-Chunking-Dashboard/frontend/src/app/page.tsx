'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import * as api from '@/lib/api';

// ─── Constants ──────────────────────────────────────────────────────

const TABS = ['Upload & Analyze', 'Chunks Explorer', 'Neo4j', 'Activity Log'] as const;
type Tab = typeof TABS[number];

const COLORS = ['#818cf8', '#a78bfa', '#c084fc', '#e879f9', '#f472b6', '#fb923c', '#34d399', '#60a5fa'];
const CONTENT_TYPE_COLORS: Record<string, string> = {
  prose: '#818cf8',
  definition: '#a78bfa',
  table: '#c084fc',
  list: '#e879f9',
  reserved: '#475569',
  fee_schedule: '#fb923c',
  technical: '#34d399',
};

// ─── Main Dashboard ─────────────────────────────────────────────────

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<Tab>('Upload & Analyze');
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [jobs, setJobs] = useState<any[]>([]);

  // Load existing jobs on mount
  useEffect(() => {
    api.getJobs().then(setJobs).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen bg-dark-900">
      {/* Header */}
      <header className="border-b border-dark-700 bg-dark-850 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-primary-500 to-purple-500 flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-semibold text-dark-50">Legal PDF Chunking Dashboard</h1>
              <p className="text-xs text-dark-400">Structure-Aware Chunking + FEA Graph Pipeline</p>
            </div>
          </div>
          {currentJobId && (
            <div className="flex items-center gap-2 text-sm text-dark-400">
              <span className="h-2 w-2 rounded-full bg-green-400"></span>
              Job: <span className="font-mono text-primary-400">{currentJobId}</span>
            </div>
          )}
        </div>
      </header>

      {/* Tab Bar */}
      <nav className="border-b border-dark-700 bg-dark-850 px-6">
        <div className="flex gap-1">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-3 text-sm font-medium transition-all border-b-2 ${
                activeTab === tab
                  ? 'border-primary-500 text-primary-400'
                  : 'border-transparent text-dark-400 hover:text-dark-200 hover:border-dark-500'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </nav>

      {/* Content */}
      <main className="p-6 max-w-[1600px] mx-auto">
        {activeTab === 'Upload & Analyze' && (
          <UploadTab
            currentJobId={currentJobId}
            setCurrentJobId={setCurrentJobId}
            jobs={jobs}
            setJobs={setJobs}
          />
        )}
        {activeTab === 'Chunks Explorer' && (
          <ChunksTab jobId={currentJobId} />
        )}
        {activeTab === 'Neo4j' && (
          <Neo4jTab jobId={currentJobId} />
        )}
        {activeTab === 'Activity Log' && (
          <LogTab />
        )}
      </main>
    </div>
  );
}

// ─── Tab 1: Upload & Analyze ────────────────────────────────────────

function UploadTab({
  currentJobId, setCurrentJobId, jobs, setJobs,
}: {
  currentJobId: string | null;
  setCurrentJobId: (id: string | null) => void;
  jobs: any[];
  setJobs: (jobs: any[]) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [enrich, setEnrich] = useState(true);
  const [job, setJob] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [tree, setTree] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll job status
  useEffect(() => {
    if (!currentJobId) return;
    const poll = async () => {
      try {
        const j = await api.getJob(currentJobId);
        setJob(j);
        if (j.status === 'done') {
          const s = await api.getJobStats(currentJobId);
          setStats(s);
          try { setTree(await api.getHierarchyTree(currentJobId)); } catch {}
          if (pollRef.current) clearInterval(pollRef.current);
        } else if (j.status === 'error') {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch {}
    };
    poll();
    pollRef.current = setInterval(poll, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [currentJobId]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setStats(null);
    setTree(null);
    try {
      const result = await api.uploadPDF(file, enrich);
      setCurrentJobId(result.job_id);
      setJob({ ...result, status: 'pending', progress: 0 });
    } catch (e: any) {
      alert(e.message);
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file?.name.toLowerCase().endsWith('.pdf')) handleUpload(file);
  };

  const handleSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
  };

  const statusColor = (s: string) => {
    switch (s) {
      case 'done': return 'text-green-400';
      case 'error': return 'text-red-400';
      case 'pushing': return 'text-yellow-400';
      default: return 'text-primary-400';
    }
  };

  const pieData = stats?.content_type_breakdown
    ? Object.entries(stats.content_type_breakdown).map(([name, value]) => ({ name, value }))
    : [];

  const histData = stats?.token_distribution
    ? Object.entries(stats.token_distribution).map(([range, count]) => ({ range, count }))
    : [];

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Upload Zone */}
      <div
        className={`border-2 border-dashed rounded-xl p-12 text-center transition-all cursor-pointer ${
          dragging
            ? 'border-primary-400 bg-primary-500/10'
            : 'border-dark-600 hover:border-dark-400 bg-dark-800/50'
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={handleSelect}
        />
        <svg className="w-12 h-12 mx-auto text-dark-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
        </svg>
        <p className="text-dark-300 text-lg">
          {uploading ? 'Uploading...' : 'Drop a legal PDF here or click to browse'}
        </p>
        <p className="text-dark-500 text-sm mt-1">Supports any municipal code, ordinance, or legal document</p>

        {/* Options toggles */}
        <div className="mt-4 flex items-center justify-center gap-6">
          <label className="flex items-center gap-2 text-sm text-dark-400 cursor-pointer">
            <input
              type="checkbox"
              checked={enrich}
              onChange={(e) => { e.stopPropagation(); setEnrich(e.target.checked); }}
              className="rounded border-dark-500 bg-dark-700 text-primary-500 focus:ring-primary-500"
              onClick={(e) => e.stopPropagation()}
            />
            LLM contextual enrichment (OpenRouter)
          </label>
          <span className="text-xs text-dark-500 border border-dark-600 rounded px-2 py-1">
            Extraction: Docling v2 (batched)
          </span>
        </div>
      </div>

      {/* Previous jobs selector */}
      {jobs.length > 0 && (
        <div className="flex items-center gap-3">
          <span className="text-sm text-dark-400">Previous uploads:</span>
          <div className="flex gap-2 flex-wrap">
            {jobs.slice(0, 10).map((j: any) => (
              <button
                key={j.job_id}
                onClick={() => setCurrentJobId(j.job_id)}
                className={`px-3 py-1 rounded-lg text-xs font-mono transition-all ${
                  currentJobId === j.job_id
                    ? 'bg-primary-500/20 text-primary-400 border border-primary-500/40'
                    : 'bg-dark-800 text-dark-400 border border-dark-700 hover:border-dark-500'
                }`}
              >
                {j.filename?.slice(0, 30)} ({j.job_id})
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Processing Status */}
      {job && job.status !== 'done' && job.status !== 'error' && (
        <div className="bg-dark-800 rounded-xl p-6 border border-dark-700">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-dark-200">
              Processing: {job.filename}
            </span>
            <div className="flex items-center gap-3">
              <span className="text-xs font-mono text-dark-400">
                {job.elapsed_s ? `${job.elapsed_s}s elapsed` : ''}
              </span>
              <span className={`text-sm font-medium capitalize ${statusColor(job.status)}`}>
                {job.status}
              </span>
            </div>
          </div>
          <div className="w-full bg-dark-700 rounded-full h-2.5">
            <div
              className="progress-bar h-2.5 rounded-full transition-all duration-500"
              style={{ width: `${Math.max((job.progress || 0) * 100, 2)}%` }}
            />
          </div>
          <div className="flex items-center justify-between mt-2">
            <p className="text-xs text-dark-400 font-mono">
              {job.status_detail || (
                job.status === 'extracting' ? 'Extracting text with Docling (this can take a few minutes for large PDFs)...' :
                job.status === 'chunking' ? 'Building hierarchy and creating chunks...' :
                job.status === 'enriching' ? 'Generating LLM contextual prefixes...' :
                job.status === 'pending' ? 'Queued for processing...' : ''
              )}
            </p>
            <span className="text-xs text-dark-500">
              {Math.round((job.progress || 0) * 100)}%
            </span>
          </div>
        </div>
      )}

      {/* Error State */}
      {job?.status === 'error' && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6">
          <h3 className="text-red-400 font-medium">Processing Failed</h3>
          <p className="text-red-300/70 text-sm mt-1">{job.error}</p>
        </div>
      )}

      {/* Stats Dashboard */}
      {stats && (
        <>
          {/* Stat Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
            {[
              { label: 'Pages', value: stats.total_pages, icon: '📄' },
              { label: 'Sections', value: stats.total_sections, icon: '📑' },
              { label: 'Subsections', value: stats.total_subsections, icon: '📋' },
              { label: 'Definitions', value: stats.total_definitions, icon: '📖' },
              { label: 'Tables', value: stats.total_tables, icon: '📊' },
              { label: 'Cross-Refs', value: stats.total_cross_references, icon: '🔗' },
              { label: 'Total Chunks', value: stats.total_chunks, icon: '🧩' },
            ].map(({ label, value, icon }) => (
              <div key={label} className="bg-dark-800 rounded-xl p-4 border border-dark-700">
                <div className="text-2xl mb-1">{icon}</div>
                <div className="text-2xl font-bold text-dark-50">{value}</div>
                <div className="text-xs text-dark-400 mt-1">{label}</div>
              </div>
            ))}
          </div>

          {/* Token Stats */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-dark-800 rounded-xl p-4 border border-dark-700 text-center">
              <div className="text-xl font-bold text-primary-400">{stats.avg_chunk_tokens}</div>
              <div className="text-xs text-dark-400">Avg Tokens/Chunk</div>
            </div>
            <div className="bg-dark-800 rounded-xl p-4 border border-dark-700 text-center">
              <div className="text-xl font-bold text-green-400">{stats.min_chunk_tokens}</div>
              <div className="text-xs text-dark-400">Min Tokens</div>
            </div>
            <div className="bg-dark-800 rounded-xl p-4 border border-dark-700 text-center">
              <div className="text-xl font-bold text-orange-400">{stats.max_chunk_tokens}</div>
              <div className="text-xs text-dark-400">Max Tokens</div>
            </div>
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Token Distribution */}
            <div className="bg-dark-800 rounded-xl p-6 border border-dark-700">
              <h3 className="text-sm font-medium text-dark-200 mb-4">Chunk Token Distribution</h3>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={histData}>
                  <XAxis dataKey="range" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#f1f5f9' }}
                  />
                  <Bar dataKey="count" fill="#818cf8" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Content Type Breakdown */}
            <div className="bg-dark-800 rounded-xl p-6 border border-dark-700">
              <h3 className="text-sm font-medium text-dark-200 mb-4">Content Type Breakdown</h3>
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={90}
                    label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                    labelLine={{ stroke: '#64748b' }}
                  >
                    {pieData.map((entry: any, index: number) => (
                      <Cell
                        key={entry.name}
                        fill={CONTENT_TYPE_COLORS[entry.name] || COLORS[index % COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#f1f5f9' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Hierarchy Tree */}
          {tree && (
            <div className="bg-dark-800 rounded-xl p-6 border border-dark-700">
              <h3 className="text-sm font-medium text-dark-200 mb-4">Document Structure</h3>
              <div className="max-h-96 overflow-y-auto">
                <TreeView data={tree} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── Tree View Component ────────────────────────────────────────────

function TreeView({ data, depth = 0 }: { data: any; depth?: number }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (key: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  if (!data || typeof data !== 'object') return null;

  return (
    <div className="space-y-0.5">
      {Object.entries(data).map(([key, value]: [string, any]) => {
        const hasChildren = value?.children && Object.keys(value.children).length > 0;
        const isExpanded = expanded.has(key);
        const chunkCount = value?.chunk_count || 0;

        return (
          <div key={key} style={{ paddingLeft: depth * 16 }}>
            <div
              className="flex items-center gap-2 py-1 px-2 rounded hover:bg-dark-700/50 cursor-pointer text-sm"
              onClick={() => hasChildren && toggle(key)}
            >
              {hasChildren ? (
                <span className="text-dark-400 w-4 text-center">
                  {isExpanded ? '▾' : '▸'}
                </span>
              ) : (
                <span className="w-4 text-center text-dark-600">·</span>
              )}
              <span className="text-dark-200 truncate flex-1">{key}</span>
              <span className="text-xs text-dark-500 tabular-nums">
                {chunkCount} chunk{chunkCount !== 1 ? 's' : ''}
              </span>
            </div>
            {isExpanded && hasChildren && (
              <TreeView data={value.children} depth={depth + 1} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Tab 2: Chunks Explorer ─────────────────────────────────────────

function ChunksTab({ jobId }: { jobId: string | null }) {
  const [chunks, setChunks] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [contentType, setContentType] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [pushing, setPushing] = useState(false);
  const [pushResult, setPushResult] = useState<any>(null);
  const [exporting, setExporting] = useState(false);
  const [exportResult, setExportResult] = useState<any>(null);

  useEffect(() => {
    if (!jobId) return;
    api.getJobChunks(jobId, page, 50, contentType || undefined, search || undefined)
      .then((res) => { setChunks(res.chunks); setTotal(res.total); })
      .catch(() => {});
  }, [jobId, page, contentType, search]);

  const handlePush = async () => {
    if (!jobId) return;
    setPushing(true);
    setPushResult(null);
    try {
      const result = await api.pushToNeo4j(jobId);
      setPushResult(result);
    } catch (e: any) {
      setPushResult({ error: e.message });
    } finally {
      setPushing(false);
    }
  };

  const handleExport = async () => {
    if (!jobId) return;
    setExporting(true);
    setExportResult(null);
    try {
      const result = await api.exportChunks(jobId);
      setExportResult(result);
    } catch (e: any) {
      setExportResult({ error: e.message });
    } finally {
      setExporting(false);
    }
  };

  const handleDownload = () => {
    if (!jobId) return;
    window.open(api.downloadChunksUrl(jobId), '_blank');
  };

  const toggleExpand = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  if (!jobId) {
    return (
      <div className="text-center py-20 text-dark-400">
        <p className="text-lg">No document selected</p>
        <p className="text-sm mt-1">Upload a PDF in the Upload tab first</p>
      </div>
    );
  }

  const totalPages = Math.ceil(total / 50);

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Toolbar */}
      <div className="flex items-center gap-4 flex-wrap">
        <input
          type="text"
          placeholder="Search chunks..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          className="flex-1 min-w-[200px] bg-dark-800 border border-dark-600 rounded-lg px-4 py-2 text-sm text-dark-100 placeholder-dark-500 focus:outline-none focus:border-primary-500"
        />
        <select
          value={contentType}
          onChange={(e) => { setContentType(e.target.value); setPage(1); }}
          className="bg-dark-800 border border-dark-600 rounded-lg px-4 py-2 text-sm text-dark-100 focus:outline-none focus:border-primary-500"
        >
          <option value="">All types</option>
          <option value="prose">Prose</option>
          <option value="definition">Definition</option>
          <option value="table">Table</option>
          <option value="list">List</option>
          <option value="reserved">Reserved</option>
          <option value="fee_schedule">Fee Schedule</option>
          <option value="technical">Technical</option>
        </select>
        <button
          onClick={handlePush}
          disabled={pushing}
          className="px-4 py-2 bg-gradient-to-r from-primary-600 to-purple-600 hover:from-primary-500 hover:to-purple-500 text-white rounded-lg text-sm font-medium transition-all disabled:opacity-50 flex items-center gap-2"
        >
          {pushing ? (
            <>
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
              Pushing...
            </>
          ) : (
            <>Push to Neo4j</>
          )}
        </button>
        <button
          onClick={handleExport}
          disabled={exporting}
          className="px-4 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white rounded-lg text-sm font-medium transition-all disabled:opacity-50 flex items-center gap-2"
        >
          {exporting ? (
            <>
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
              Exporting...
            </>
          ) : (
            <>Export to Disk</>
          )}
        </button>
        <button
          onClick={handleDownload}
          className="px-4 py-2 bg-dark-700 hover:bg-dark-600 text-dark-200 border border-dark-500 rounded-lg text-sm font-medium transition-all flex items-center gap-2"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
          Download JSON
        </button>
        <span className="text-sm text-dark-400">{total} chunks</span>
      </div>

      {/* Push Result */}
      {pushResult && (
        <div className={`rounded-lg p-4 text-sm ${pushResult.error ? 'bg-red-500/10 border border-red-500/30 text-red-300' : 'bg-green-500/10 border border-green-500/30 text-green-300'}`}>
          {pushResult.error ? (
            <p>Push failed: {pushResult.error}</p>
          ) : (
            <p>
              Pushed successfully: {pushResult.stats?.chunks_created} chunks, {pushResult.stats?.sections_created} sections,{' '}
              {pushResult.stats?.cross_ref_edges} cross-ref edges, {pushResult.stats?.threshold_nodes} thresholds,{' '}
              {pushResult.stats?.penalty_nodes} penalties, {pushResult.stats?.role_nodes} roles,{' '}
              {pushResult.stats?.obligation_nodes} obligations
            </p>
          )}
        </div>
      )}

      {/* Export Result */}
      {exportResult && (
        <div className={`rounded-lg p-4 text-sm ${exportResult.error ? 'bg-red-500/10 border border-red-500/30 text-red-300' : 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-300'}`}>
          {exportResult.error ? (
            <p>Export failed: {exportResult.error}</p>
          ) : (
            <p>
              Exported {exportResult.chunk_count} chunks to <span className="font-mono text-xs">{exportResult.export_path}</span>
              {' '}({exportResult.files?.join(', ')})
            </p>
          )}
        </div>
      )}

      {/* Chunks List */}
      <div className="space-y-2">
        {chunks.map((chunk: any) => {
          const meta = chunk.metadata;
          const isOpen = expanded.has(meta.chunk_id);
          return (
            <div key={meta.chunk_id} className="bg-dark-800 border border-dark-700 rounded-xl overflow-hidden">
              <div
                className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-dark-700/50 transition-all"
                onClick={() => toggleExpand(meta.chunk_id)}
              >
                <span className="text-dark-400 w-4">{isOpen ? '▾' : '▸'}</span>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  meta.content_type === 'definition' ? 'bg-purple-500/20 text-purple-300' :
                  meta.content_type === 'table' ? 'bg-pink-500/20 text-pink-300' :
                  meta.content_type === 'list' ? 'bg-fuchsia-500/20 text-fuchsia-300' :
                  meta.content_type === 'reserved' ? 'bg-dark-600 text-dark-400' :
                  meta.content_type === 'fee_schedule' ? 'bg-orange-500/20 text-orange-300' :
                  'bg-primary-500/20 text-primary-300'
                }`}>
                  {meta.content_type}
                </span>
                <span className="text-sm text-dark-200 truncate flex-1">{meta.breadcrumb}</span>
                <span className="text-xs text-dark-500 tabular-nums">{meta.token_count} tokens</span>
                {meta.cross_references?.length > 0 && (
                  <span className="text-xs text-blue-400">
                    {meta.cross_references.length} refs
                  </span>
                )}
              </div>
              {isOpen && (
                <div className="px-4 pb-4 border-t border-dark-700 pt-3 space-y-3">
                  {chunk.context_prefix && (
                    <div className="bg-primary-500/5 border border-primary-500/20 rounded-lg p-3 text-sm text-primary-200 italic">
                      {chunk.context_prefix}
                    </div>
                  )}
                  <pre className="text-sm text-dark-300 whitespace-pre-wrap font-mono bg-dark-900/50 rounded-lg p-4 max-h-64 overflow-y-auto">
                    {chunk.text}
                  </pre>
                  <div className="flex flex-wrap gap-2 text-xs">
                    {meta.cross_references?.map((ref: string) => (
                      <span key={ref} className="px-2 py-0.5 bg-blue-500/10 text-blue-400 rounded">
                        &sect; {ref}
                      </span>
                    ))}
                    {meta.ordinance_citations?.map((cit: string) => (
                      <span key={cit} className="px-2 py-0.5 bg-amber-500/10 text-amber-400 rounded">
                        Ord. {cit}
                      </span>
                    ))}
                    {meta.dollar_amounts_present && (
                      <span className="px-2 py-0.5 bg-green-500/10 text-green-400 rounded">$ amounts</span>
                    )}
                  </div>
                  <div className="text-xs text-dark-500 font-mono">
                    ID: {meta.chunk_id} | Pages: {meta.page_range}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-4">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="px-3 py-1 bg-dark-800 border border-dark-600 rounded text-sm text-dark-300 disabled:opacity-30 hover:border-dark-400"
          >
            Prev
          </button>
          <span className="text-sm text-dark-400">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="px-3 py-1 bg-dark-800 border border-dark-600 rounded text-sm text-dark-300 disabled:opacity-30 hover:border-dark-400"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Tab 3: Neo4j ───────────────────────────────────────────────────

function Neo4jTab({ jobId }: { jobId: string | null }) {
  const [status, setStatus] = useState<any>(null);
  const [query, setQuery] = useState('MATCH (n) RETURN labels(n) AS label, count(n) AS count ORDER BY count DESC LIMIT 20');
  const [queryResult, setQueryResult] = useState<any>(null);
  const [querying, setQuerying] = useState(false);

  useEffect(() => {
    api.getNeo4jStatus().then(setStatus).catch(() => setStatus({ connected: false }));
  }, []);

  const runQuery = async () => {
    setQuerying(true);
    setQueryResult(null);
    try {
      const result = await api.runCypherQuery(query);
      setQueryResult(result);
    } catch (e: any) {
      setQueryResult({ error: e.message });
    } finally {
      setQuerying(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Connection Status */}
      <div className="bg-dark-800 rounded-xl p-6 border border-dark-700">
        <div className="flex items-center gap-3 mb-4">
          <div className={`h-3 w-3 rounded-full ${status?.connected ? 'bg-green-400 pulse-glow' : 'bg-red-400'}`} />
          <h3 className="text-lg font-medium text-dark-100">
            Neo4j {status?.connected ? 'Connected' : 'Disconnected'}
          </h3>
          <span className="text-sm text-dark-500">({status?.mode || 'unknown'} mode)</span>
        </div>
        {status?.connected && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-primary-400">{status.total_nodes?.toLocaleString()}</div>
              <div className="text-xs text-dark-400">Total Nodes</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-purple-400">{status.total_relationships?.toLocaleString()}</div>
              <div className="text-xs text-dark-400">Relationships</div>
            </div>
            <div className="text-center">
              <div className="text-sm text-dark-300">{status.uri}</div>
              <div className="text-xs text-dark-400">URI</div>
            </div>
            <div className="text-center">
              <div className="text-sm text-dark-300">{status.last_push || 'Never'}</div>
              <div className="text-xs text-dark-400">Last Push</div>
            </div>
          </div>
        )}
        {!status?.connected && status?.error && (
          <p className="text-sm text-red-300/70">{status.error}</p>
        )}
      </div>

      {/* Cypher Query Box */}
      <div className="bg-dark-800 rounded-xl p-6 border border-dark-700">
        <h3 className="text-sm font-medium text-dark-200 mb-3">Cypher Query</h3>
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={4}
          className="w-full bg-dark-900 border border-dark-600 rounded-lg p-4 text-sm font-mono text-dark-100 placeholder-dark-500 focus:outline-none focus:border-primary-500 resize-y"
          placeholder="Enter a Cypher query..."
        />
        <button
          onClick={runQuery}
          disabled={querying}
          className="mt-3 px-4 py-2 bg-primary-600 hover:bg-primary-500 text-white rounded-lg text-sm font-medium transition-all disabled:opacity-50"
        >
          {querying ? 'Running...' : 'Run Query'}
        </button>
      </div>

      {/* Query Results */}
      {queryResult && (
        <div className="bg-dark-800 rounded-xl p-6 border border-dark-700">
          <h3 className="text-sm font-medium text-dark-200 mb-3">Results</h3>
          {queryResult.error ? (
            <p className="text-red-400 text-sm">{queryResult.error}</p>
          ) : (
            <div className="overflow-x-auto">
              {queryResult.results?.length > 0 ? (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-dark-600">
                      {Object.keys(queryResult.results[0]).map((key: string) => (
                        <th key={key} className="text-left py-2 px-3 text-dark-400 font-medium">{key}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {queryResult.results.map((row: any, i: number) => (
                      <tr key={i} className="border-b border-dark-700/50 hover:bg-dark-700/30">
                        {Object.values(row).map((val: any, j: number) => (
                          <td key={j} className="py-2 px-3 text-dark-300 font-mono">
                            {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="text-dark-400">No results</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Quick Actions */}
      <div className="bg-dark-800 rounded-xl p-6 border border-dark-700">
        <h3 className="text-sm font-medium text-dark-200 mb-3">Quick Queries</h3>
        <div className="flex flex-wrap gap-2">
          {[
            { label: 'Node counts by label', q: 'MATCH (n) RETURN labels(n) AS label, count(n) AS count ORDER BY count DESC' },
            { label: 'Relationship types', q: 'MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count ORDER BY count DESC' },
            { label: 'Top cross-referenced sections', q: 'MATCH (c:Chunk)-[:REFERENCES]->(t:Chunk) RETURN t.section_number AS section, t.breadcrumb AS breadcrumb, count(c) AS referenced_by ORDER BY referenced_by DESC LIMIT 15' },
            { label: 'All roles mentioned', q: 'MATCH (r:Role)<-[:MENTIONS_ROLE]-(c:Chunk) RETURN r.name AS role, count(c) AS mentioned_in ORDER BY mentioned_in DESC' },
            { label: 'Penalty amounts', q: 'MATCH (c:Chunk)-[:HAS_PENALTY]->(p:Penalty) RETURN p.amount AS amount, c.breadcrumb AS section LIMIT 20' },
            { label: 'Documents pushed', q: 'MATCH (d:Document) RETURN d.name AS document, d.jurisdiction AS jurisdiction, d.chunk_count AS chunks, d.pushed_at AS pushed_at' },
          ].map(({ label, q }) => (
            <button
              key={label}
              onClick={() => { setQuery(q); }}
              className="px-3 py-1.5 bg-dark-700 hover:bg-dark-600 border border-dark-600 rounded-lg text-xs text-dark-300 transition-all"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Tab 4: Activity Log ────────────────────────────────────────────

function LogTab() {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.getLogs()
      .then(setLogs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="text-center py-20 text-dark-400">Loading logs...</div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="bg-dark-800 rounded-xl border border-dark-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-dark-850 border-b border-dark-600">
                <th className="text-left py-3 px-4 text-dark-400 font-medium">Document</th>
                <th className="text-left py-3 px-4 text-dark-400 font-medium">Upload Time</th>
                <th className="text-right py-3 px-4 text-dark-400 font-medium">Pages</th>
                <th className="text-right py-3 px-4 text-dark-400 font-medium">Chunks</th>
                <th className="text-center py-3 px-4 text-dark-400 font-medium">Enriched</th>
                <th className="text-center py-3 px-4 text-dark-400 font-medium">Neo4j</th>
                <th className="text-left py-3 px-4 text-dark-400 font-medium">Push Time</th>
                <th className="text-right py-3 px-4 text-dark-400 font-medium">Duration</th>
                <th className="text-center py-3 px-4 text-dark-400 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={9} className="text-center py-12 text-dark-500">No activity yet</td>
                </tr>
              ) : (
                logs.map((log: any) => (
                  <tr key={log.id} className="border-b border-dark-700/50 hover:bg-dark-700/30">
                    <td className="py-3 px-4 text-dark-200 font-medium truncate max-w-[200px]">{log.filename}</td>
                    <td className="py-3 px-4 text-dark-400 text-xs">
                      {new Date(log.upload_time).toLocaleString()}
                    </td>
                    <td className="py-3 px-4 text-right text-dark-300 tabular-nums">{log.page_count}</td>
                    <td className="py-3 px-4 text-right text-dark-300 tabular-nums">{log.chunk_count}</td>
                    <td className="py-3 px-4 text-center">
                      {log.enrichment_enabled ? (
                        <span className="text-green-400">Yes</span>
                      ) : (
                        <span className="text-dark-500">No</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-center">
                      {log.pushed_to_neo4j ? (
                        <span className="inline-flex items-center gap-1 text-green-400">
                          <span className="h-1.5 w-1.5 rounded-full bg-green-400"></span>
                          Pushed
                        </span>
                      ) : (
                        <span className="text-dark-500">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-dark-400 text-xs">
                      {log.push_time ? new Date(log.push_time).toLocaleString() : '—'}
                    </td>
                    <td className="py-3 px-4 text-right text-dark-300 tabular-nums">
                      {log.processing_duration_s ? `${log.processing_duration_s.toFixed(1)}s` : '—'}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        log.status === 'done' ? 'bg-green-500/20 text-green-300' :
                        log.status === 'error' ? 'bg-red-500/20 text-red-300' :
                        'bg-yellow-500/20 text-yellow-300'
                      }`}>
                        {log.status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
