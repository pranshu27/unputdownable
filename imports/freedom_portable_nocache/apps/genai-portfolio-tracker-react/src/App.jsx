import { useState, useCallback, useEffect, useRef } from 'react'
import { INITIAL_DATA } from './data.js'
import Dashboard from './components/Dashboard.jsx'
import Projects from './components/Projects.jsx'
import Weekly from './components/Weekly.jsx'
import Risks from './components/Risks.jsx'
import Journal from './components/Journal.jsx'
import Interview from './components/Interview.jsx'

const STORAGE_KEY = 'genai-tracker-v3'
const SYNC_META_KEY = 'genai-tracker-sync-meta-v1'
const UNSYNCED_DRAFT_KEY = 'genai-tracker-unsynced-draft-v1'
const API = 'http://localhost:8001'
const SEED_REVISION = '2026-08-18-doc-refresh-v2'
const LEGACY_P1_NOTE = 'W1-W2 complete for core retrieval stack; W3 will focus on evaluation dataset and RAGAS baselines.'
const LEGACY_W4_NOTE =
  'W4 complete on quality guardrails and docs alignment: semantic-first architecture docs refreshed, NetworkX graph lineage integrated, cross-workflow deterministic tracing delivered, and analytics notebook scaffolded for PostgreSQL deep-dive.'

function normalizeLabel(label) {
  return String(label || '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
}

function mergeChecklist(seedItems, storedItems) {
  const byId = Object.fromEntries((storedItems || []).map(item => [item.id, item]))
  const byLabel = Object.fromEntries(
    (storedItems || []).map(item => [normalizeLabel(item.label), item])
  )

  return (seedItems || []).map(seed => {
    const stored = byId[seed.id] || byLabel[normalizeLabel(seed.label)] || null
    return {
      ...seed,
      // Seeded completions are authoritative; otherwise preserve user completion when available.
      done: seed.done || !!stored?.done,
    }
  })
}

// ── Merge stored state with INITIAL_DATA (new content always propagates) ──
function mergeWithInitial(stored) {
  const base = stored ? { ...stored } : { ...INITIAL_DATA }
    const prevSeedRevision = String(stored?.meta?.seedRevision || '')
    const sessionKey = (s) => `${String(s?.date || '').trim()}::${String(s?.title || '').trim()}`
    const seededStoriesById = Object.fromEntries((INITIAL_DATA.journal?.stories || []).map(s => [s.id, s]))
    const seededSessionsByKey = Object.fromEntries((INITIAL_DATA.interview?.sessions || []).map(s => [sessionKey(s), s]))
    // Merge in new top-level keys added after initial release (backward compat)
    if (!base.interview)  base.interview  = INITIAL_DATA.interview
    // Always sync qbank and weeks from INITIAL_DATA so new content is immediately visible
    // (preserves user's done-states + notes by merging task by ID)
    if (base.interview) {
      base.interview.qbank = INITIAL_DATA.interview?.qbank || []
      // Merge new sessions from INITIAL_DATA (keyed by date+title to allow multiple same-day sessions).
      const existingSessionKeys = new Set((base.interview.sessions || []).map(sessionKey))
      const newSessions = (INITIAL_DATA.interview?.sessions || []).filter(s => !existingSessionKeys.has(sessionKey(s)))
      if (newSessions.length) {
        base.interview.sessions = [...(base.interview.sessions || []), ...newSessions]
      }
      // Keep canonical STAR summaries current for seeded sessions.
      base.interview.sessions = (base.interview.sessions || []).map(s => {
        const seeded = seededSessionsByKey[sessionKey(s)]
        return seeded?.star_story ? { ...s, star_story: seeded.star_story } : s
      })
    }
    // Merge journal: pull any new daily entries and STAR stories from INITIAL_DATA
    if (!base.journal) {
      base.journal = INITIAL_DATA.journal || { daily: [], stories: [] }
    } else {
      const existingDailyIds = new Set((base.journal.daily || []).map(e => e.id))
      const newDaily = (INITIAL_DATA.journal?.daily || []).filter(e => !existingDailyIds.has(e.id))
      if (newDaily.length) base.journal.daily = [...(base.journal.daily || []), ...newDaily]

      const existingStoryIds = new Set((base.journal.stories || []).map(s => s.id))
      const newStories = (INITIAL_DATA.journal?.stories || []).filter(s => !existingStoryIds.has(s.id))
      if (newStories.length) base.journal.stories = [...(base.journal.stories || []), ...newStories]
      // Keep canonical STAR stories current for seeded IDs.
      base.journal.stories = (base.journal.stories || []).map(s => {
        const seeded = seededStoriesById[s.id]
        return seeded ? { ...s, ...seeded } : s
      })
    }
    if (INITIAL_DATA.projects?.length) {
      const storedProjectsById = Object.fromEntries((base.projects || []).map(p => [p.id, p]))
      base.projects = INITIAL_DATA.projects.map(project => {
        const storedProject = storedProjectsById[project.id] || {}

        let status = storedProject.status || project.status
        if (project.status === 'in-progress' && status === 'not-started') status = 'in-progress'
        if (project.status === 'done') status = 'done'

        const storedNotes = String(storedProject.notes || '')
        const shouldMigrateP1Notes =
          project.id === 1 &&
          (!storedNotes || storedNotes === LEGACY_P1_NOTE || prevSeedRevision !== SEED_REVISION)

        return {
          ...project,
          status,
          notes: shouldMigrateP1Notes ? project.notes : (storedProject.notes || project.notes),
          milestones: mergeChecklist(project.milestones, storedProject.milestones || [])
        }
      })
    }
    if (INITIAL_DATA.weeks?.length) {
      base.weeks = INITIAL_DATA.weeks.map(w => {
        const storedWeek = (base.weeks || []).find(sw => sw.week === w.week) || {}
        const storedNotes = String(storedWeek.notes || '')
        const shouldMigrateWeek4Note =
          w.week === 4 && normalizeLabel(storedNotes) === normalizeLabel(LEGACY_W4_NOTE)
        return {
          ...w,
          notes: shouldMigrateWeek4Note ? w.notes : (storedNotes || w.notes),
          tasks: mergeChecklist(w.tasks, storedWeek.tasks || [])
        }
      })
    }
    if (INITIAL_DATA.risks?.length) {
      const storedRisks = base.risks || []
      const storedRisksById = Object.fromEntries(storedRisks.map(r => [r.id, r]))
      const seededRiskIds = new Set((INITIAL_DATA.risks || []).map(r => r.id))

      const seededMerged = INITIAL_DATA.risks.map(risk => {
        const storedRisk = storedRisksById[risk.id] || {}
        return {
          ...risk,
          // Preserve user lifecycle state while keeping seeded documentation current.
          status: storedRisk.status || risk.status,
        }
      })

      const customRisks = storedRisks.filter(r => !seededRiskIds.has(r.id))
      base.risks = [...seededMerged, ...customRisks]
    }
    base.meta = { ...(base.meta || {}), seedRevision: SEED_REVISION }
    return base
}

function load() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return mergeWithInitial(stored ? JSON.parse(stored) : null)
  } catch {
    return mergeWithInitial(null)
  }
}

function persistLocal(data) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(data)) } catch {}
}

function loadSyncMeta() {
  try {
    const raw = localStorage.getItem(SYNC_META_KEY)
    if (!raw) return { lastAckVersion: 0, dirty: false, conflict: false, lastAckAt: null }
    const parsed = JSON.parse(raw)
    return {
      lastAckVersion: Number(parsed?.lastAckVersion || 0),
      dirty: !!parsed?.dirty,
      conflict: !!parsed?.conflict,
      lastAckAt: parsed?.lastAckAt || null,
      error: parsed?.error || null,
    }
  } catch {
    return { lastAckVersion: 0, dirty: false, conflict: false, lastAckAt: null }
  }
}

function persistSyncMeta(meta) {
  try { localStorage.setItem(SYNC_META_KEY, JSON.stringify(meta)) } catch {}
}

function markUnsyncedDraft(data) {
  try {
    localStorage.setItem(
      UNSYNCED_DRAFT_KEY,
      JSON.stringify({ data, capturedAt: new Date().toISOString() })
    )
  } catch {}
}

function clearUnsyncedDraft() {
  try { localStorage.removeItem(UNSYNCED_DRAFT_KEY) } catch {}
}

async function fetchServerState() {
  const r = await fetch(`${API}/api/state`)
  if (!r.ok) return { data: {}, version: 0, updated_at: null }
  const payload = await r.json().catch(() => ({}))

  // Backward compatibility: if backend still returns plain state dict.
  if (
    payload &&
    typeof payload === 'object' &&
    !Array.isArray(payload) &&
    ('data' in payload || 'version' in payload)
  ) {
    return {
      data: payload.data || {},
      version: Number(payload.version || 0),
      updated_at: payload.updated_at || null,
    }
  }

  return {
    data: payload && typeof payload === 'object' ? payload : {},
    version: 0,
    updated_at: null,
  }
}

async function persistBackend(data, expectedVersion) {
  try {
    const r = await fetch(`${API}/api/state`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data, expected_version: expectedVersion }),
    })
    const payload = await r.json().catch(() => ({}))

    if (r.status === 409) {
      return { ok: false, conflict: true, server: payload?.server || null }
    }
    if (!r.ok || payload?.status === 'error') {
      return {
        ok: false,
        conflict: false,
        error: payload?.detail || `HTTP ${r.status}`,
      }
    }
    return {
      ok: true,
      version: Number(payload?.version || expectedVersion),
      updatedAt: payload?.updated_at || null,
    }
  } catch (err) {
    return {
      ok: false,
      conflict: false,
      error: err?.message || 'network_error',
    }
  }
}

function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 5) }
function todayStr() { return new Date().toISOString().slice(0, 10) }

const TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: '◈' },
  { id: 'projects',  label: 'Projects',  icon: '⬡' },
  { id: 'weekly',    label: 'Weekly',    icon: '≡' },
  { id: 'risks',     label: 'Risks',     icon: '⚑' },
  { id: 'journal',   label: 'Journal',   icon: '✦' },
  { id: 'interview', label: 'Interview', icon: '⬤' },
]

const VIEWS = { dashboard: Dashboard, projects: Projects, weekly: Weekly, risks: Risks, journal: Journal, interview: Interview }

export default function App() {
  const [data, setData] = useState(load)   // instant: localStorage
  const [tab, setTab]   = useState('dashboard')
  const [syncMeta, setSyncMeta] = useState(loadSyncMeta)
  const [syncNotice, setSyncNotice] = useState('')
  const syncRef = useRef({
    inFlight: false,
    queued: null,
    version: loadSyncMeta().lastAckVersion || 0,
  })
  const conflictServerRef = useRef(null)

  useEffect(() => {
    persistSyncMeta(syncMeta)
  }, [syncMeta])

  const flushSyncQueue = useCallback(async () => {
    if (syncRef.current.inFlight) return
    syncRef.current.inFlight = true
    try {
      while (syncRef.current.queued) {
        const snapshot = syncRef.current.queued
        syncRef.current.queued = null
        const expectedVersion = syncRef.current.version || 0
        const result = await persistBackend(snapshot, expectedVersion)

        if (result.ok) {
          syncRef.current.version = Number(result.version || expectedVersion)
          clearUnsyncedDraft()
          setSyncMeta(prev => ({
            ...prev,
            lastAckVersion: syncRef.current.version,
            dirty: !!syncRef.current.queued,
            conflict: false,
            error: null,
            lastAckAt: result.updatedAt || new Date().toISOString(),
          }))
          if (!syncRef.current.queued) setSyncNotice('')
          continue
        }

        if (result.conflict) {
          markUnsyncedDraft(snapshot)
          conflictServerRef.current = result.server || null
          setSyncMeta(prev => ({ ...prev, dirty: true, conflict: true, error: 'conflict' }))
          setSyncNotice('Sync conflict detected. Local unsynced changes were preserved.')
          break
        }

        markUnsyncedDraft(snapshot)
        setSyncMeta(prev => ({
          ...prev,
          dirty: true,
          conflict: false,
          error: result.error || 'save_failed',
        }))
        setSyncNotice('Backend is unreachable. Changes are kept locally and will sync on retry.')
        break
      }
    } finally {
      syncRef.current.inFlight = false
    }
  }, [])

  const enqueueSync = useCallback((nextData) => {
    syncRef.current.queued = nextData
    if (!syncRef.current.inFlight) {
      void flushSyncQueue()
    }
  }, [flushSyncQueue])

  // Bootstrap sync state: prefer backend unless local has unsynced edits.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const localMeta = loadSyncMeta()
      const localSnapshot = load()
      try {
        const server = await fetchServerState()
        if (cancelled) return

        syncRef.current.version = Number(server.version || 0)

        // Never silently discard unsynced local edits.
        if (localMeta.dirty) {
          const mergedLocal = mergeWithInitial(localSnapshot)
          setData(mergedLocal)
          persistLocal(mergedLocal)

          if ((server.version || 0) > (localMeta.lastAckVersion || 0)) {
            conflictServerRef.current = server
            setSyncMeta(prev => ({
              ...prev,
              dirty: true,
              conflict: true,
              error: 'startup_conflict',
            }))
            setSyncNotice('Unsynced local edits detected with newer backend data. Resolve conflict before syncing.')
          } else {
            setSyncMeta(prev => ({ ...prev, dirty: true, conflict: false, error: null }))
            enqueueSync(mergedLocal)
          }
          return
        }

        if (server.data && Object.keys(server.data).length > 0) {
          const merged = mergeWithInitial(server.data)
          setData(merged)
          persistLocal(merged)
          setSyncMeta({
            lastAckVersion: Number(server.version || 0),
            dirty: false,
            conflict: false,
            error: null,
            lastAckAt: server.updated_at || null,
          })

          // If migrations changed the shape/content, write back with version check.
          if (JSON.stringify(server.data) !== JSON.stringify(merged)) {
            setSyncMeta(prev => ({ ...prev, dirty: true }))
            enqueueSync(merged)
          }
        } else {
          const seed = load()
          setData(seed)
          persistLocal(seed)
          setSyncMeta(prev => ({ ...prev, dirty: true, conflict: false, error: null }))
          enqueueSync(seed)
        }
      } catch {
        if (!cancelled) {
          setSyncNotice('Running in local-only mode until backend becomes reachable.')
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [enqueueSync])

  const update = useCallback((fn) => {
    setData(prev => {
      const next = fn(prev)
      persistLocal(next)
      markUnsyncedDraft(next)
      setSyncMeta(m => ({ ...m, dirty: true, conflict: m.conflict, error: null }))
      if (!syncMeta.conflict) {
        enqueueSync(next)
      }
      return next
    })
  }, [enqueueSync, syncMeta.conflict])

  const keepLocalAndOverwriteBackend = useCallback(async () => {
    const latest = await fetchServerState().catch(() => ({ version: syncRef.current.version || 0 }))
    syncRef.current.version = Number(latest?.version || 0)
    const result = await persistBackend(data, syncRef.current.version)

    if (result.ok) {
      syncRef.current.version = Number(result.version || syncRef.current.version)
      clearUnsyncedDraft()
      setSyncMeta(prev => ({
        ...prev,
        lastAckVersion: syncRef.current.version,
        dirty: false,
        conflict: false,
        error: null,
        lastAckAt: result.updatedAt || new Date().toISOString(),
      }))
      setSyncNotice('Local version synced to backend successfully.')
      conflictServerRef.current = null
      syncRef.current.queued = null
      return
    }

    setSyncNotice('Could not resolve conflict yet. Backend is still unreachable or changed again.')
  }, [data])

  const useBackendVersion = useCallback(() => {
    const server = conflictServerRef.current
    if (!server?.data) return

    const merged = mergeWithInitial(server.data)
    setData(merged)
    persistLocal(merged)
    clearUnsyncedDraft()
    syncRef.current.version = Number(server.version || syncRef.current.version || 0)
    setSyncMeta(prev => ({
      ...prev,
      lastAckVersion: syncRef.current.version,
      dirty: false,
      conflict: false,
      error: null,
      lastAckAt: server.updated_at || new Date().toISOString(),
    }))
    setSyncNotice('Loaded backend version. Local unsynced draft was discarded.')
    conflictServerRef.current = null
    syncRef.current.queued = null
  }, [])

  const retrySync = useCallback(() => {
    if (syncMeta.conflict) return
    enqueueSync(data)
  }, [data, enqueueSync, syncMeta.conflict])

  const actions = {
    // ── Program ──────────────────────────────────────────────────────────
    updateProgram: (field, value) => update(d => ({
      ...d, program: { ...d.program, [field]: value }
    })),

    // ── Projects ─────────────────────────────────────────────────────────
    toggleMilestone: (projectId, milestoneId) => update(d => ({
      ...d,
      projects: d.projects.map(p =>
        p.id === projectId
          ? { ...p, milestones: p.milestones.map(m => m.id === milestoneId ? { ...m, done: !m.done } : m) }
          : p
      )
    })),

    setProjectStatus: (projectId, status) => update(d => ({
      ...d, projects: d.projects.map(p => p.id === projectId ? { ...p, status } : p)
    })),

    setProjectNotes: (projectId, notes) => update(d => ({
      ...d, projects: d.projects.map(p => p.id === projectId ? { ...p, notes } : p)
    })),

    // ── Weekly ───────────────────────────────────────────────────────────
    toggleTask: (week, taskId) => update(d => ({
      ...d,
      weeks: d.weeks.map(w =>
        w.week === week
          ? { ...w, tasks: w.tasks.map(t => t.id === taskId ? { ...t, done: !t.done } : t) }
          : w
      )
    })),

    setWeekNotes: (week, notes) => update(d => ({
      ...d, weeks: d.weeks.map(w => w.week === week ? { ...w, notes } : w)
    })),

    // ── Risks ────────────────────────────────────────────────────────────
    addRisk: () => update(d => ({
      ...d,
      risks: [...d.risks, {
        id: `r${Date.now()}`, description: '', likelihood: 'medium',
        impact: 'medium', mitigation: '', status: 'open'
      }]
    })),

    updateRisk: (id, field, value) => update(d => ({
      ...d, risks: d.risks.map(r => r.id === id ? { ...r, [field]: value } : r)
    })),

    deleteRisk: (id) => update(d => ({
      ...d, risks: d.risks.filter(r => r.id !== id)
    })),

    // ── Journal — Daily ──────────────────────────────────────────────────
    addDailyEntry: () => update(d => ({
      ...d,
      journal: {
        ...d.journal,
        daily: [{
          id: uid(), type: 'daily', date: todayStr(),
          title: '', mood: '🟢', energy: 4,
          wins: [''], losses: [''], notes: '', _new: true
        }, ...(d.journal?.daily || [])]
      }
    })),

    updateDailyEntry: (id, field, value) => update(d => ({
      ...d,
      journal: {
        ...d.journal,
        daily: (d.journal?.daily || []).map(e =>
          e.id === id ? { ...e, [field]: value, _new: false } : e
        )
      }
    })),

    deleteDailyEntry: (id) => update(d => ({
      ...d,
      journal: { ...d.journal, daily: (d.journal?.daily || []).filter(e => e.id !== id) }
    })),

    // ── Journal — STAR Stories ───────────────────────────────────────────
    addStarStory: () => update(d => ({
      ...d,
      journal: {
        ...d.journal,
        stories: [{
          id: uid(), type: 'star', date: todayStr(),
          title: '', category: 'Problem Solving',
          situation: '', task: '', action: '', result: '',
          tags: [], _new: true
        }, ...(d.journal?.stories || [])]
      }
    })),

    updateStarStory: (id, field, value) => update(d => ({
      ...d,
      journal: {
        ...d.journal,
        stories: (d.journal?.stories || []).map(s =>
          s.id === id ? { ...s, [field]: value, _new: false } : s
        )
      }
    })),

    deleteStarStory: (id) => update(d => ({
      ...d,
      journal: { ...d.journal, stories: (d.journal?.stories || []).filter(s => s.id !== id) }
    })),


    // ── Interview ────────────────────────────────────────────────────────

    // -- Quiz ----------------------------------------------------------------
    recordQuizAnswer: (qid, rating) => update(d => {
      const hist = d.interview?.quiz_history || {}
      const prev = hist[qid] || { ratings: [], last_seen: null }
      return {
        ...d,
        interview: {
          ...d.interview,
          quiz_history: {
            ...hist,
            [qid]: {
              ratings: [...prev.ratings.slice(-9), rating],  // keep last 10
              last_seen: todayStr(),
              times_seen: (prev.times_seen || 0) + 1,
            }
          }
        }
      }
    }),

    addInterviewSession: () => update(d => ({
      ...d,
      interview: {
        ...d.interview,
        sessions: [{
          id: uid(), date: todayStr(), title: '', overall: 'needs_work',
          qs: [], went_well: [''], to_improve: [''], notes: '', _new: true
        }, ...(d.interview?.sessions || [])]
      }
    })),

    updateInterviewSession: (id, field, value) => update(d => ({
      ...d,
      interview: {
        ...d.interview,
        sessions: (d.interview?.sessions || []).map(s =>
          s.id === id ? { ...s, [field]: value, _new: false } : s
        )
      }
    })),

    deleteInterviewSession: (id) => update(d => ({
      ...d,
      interview: {
        ...d.interview,
        sessions: (d.interview?.sessions || []).filter(s => s.id !== id)
      }
    })),

    // ── Utilities ────────────────────────────────────────────────────────
    reset: () => {
      if (window.confirm('Reset all progress? This cannot be undone.')) {
        update(() => ({ ...INITIAL_DATA }))
      }
    },

    exportMarkdown: () => {
      const lines = []
      lines.push(`# ${data.program.name}`)
      lines.push(`> Owner: **${data.program.owner}** | ${data.program.startDate} → ${data.program.endDate}`)
      lines.push('')

      const totalM = data.projects.reduce((s, p) => s + p.milestones.length, 0)
      const doneM  = data.projects.reduce((s, p) => s + p.milestones.filter(m => m.done).length, 0)
      lines.push(`## Program Progress: ${doneM}/${totalM} milestones (${Math.round(doneM / totalM * 100)}%)`)
      lines.push('')

      for (const p of data.projects) {
        const done = p.milestones.filter(m => m.done).length
        lines.push(`### P${p.id}: ${p.name} · ${p.weekRange} · \`${p.status}\``)
        lines.push(`Progress: ${done}/${p.milestones.length}`)
        for (const m of p.milestones) lines.push(`- [${m.done ? 'x' : ' '}] ${m.label}`)
        if (p.notes) lines.push(`\n> ${p.notes}`)
        lines.push('')
      }

      lines.push('## Weekly Log')
      for (const w of data.weeks) {
        const done = w.tasks.filter(t => t.done).length
        lines.push(`### Week ${w.week}: ${w.focus} (${done}/${w.tasks.length})`)
        for (const t of w.tasks) lines.push(`- [${t.done ? 'x' : ' '}] ${t.label}`)
        if (w.notes) lines.push(`> ${w.notes}`)
        lines.push('')
      }

      if (data.risks.length) {
        lines.push('## Risk Register')
        lines.push('| Description | Likelihood | Impact | Mitigation | Status |')
        lines.push('|---|---|---|---|---|')
        for (const r of data.risks) {
          lines.push(`| ${r.description} | ${r.likelihood} | ${r.impact} | ${r.mitigation} | ${r.status} |`)
        }
      }

      const j = data.journal
      if (j?.daily?.length) {
        lines.push(''); lines.push('## Daily Journal')
        for (const e of [...j.daily].sort((a,b)=>b.date.localeCompare(a.date))) {
          lines.push(`### ${e.date} — ${e.title || 'Untitled'}`)
          if (e.wins?.length) { lines.push('**Wins:**'); e.wins.filter(Boolean).forEach(w => lines.push(`- ✅ ${w}`)) }
          if (e.losses?.length) { lines.push('**Blockers:**'); e.losses.filter(Boolean).forEach(l => lines.push(`- 🔴 ${l}`)) }
          if (e.notes) lines.push(`> ${e.notes}`)
          lines.push('')
        }
      }

      if (j?.stories?.length) {
        lines.push('## STAR Stories')
        for (const s of j.stories) {
          lines.push(`### ${s.title || 'Untitled'} (${s.category})`)
          lines.push(`**S:** ${s.situation}`); lines.push(`**T:** ${s.task}`)
          lines.push(`**A:** ${s.action}`); lines.push(`**R:** ${s.result}`)
          lines.push('')
        }
      }

      const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href = url; a.download = `portfolio-${new Date().toISOString().slice(0,10)}.md`
      a.click(); URL.revokeObjectURL(url)
    }
  }

  const View = VIEWS[tab]
  const syncStateText = syncMeta.conflict
    ? 'Conflict'
    : syncMeta.dirty
      ? 'Pending sync'
      : 'Synced'
  const activeTabLabel = TABS.find(t => t.id === tab)?.label || 'Dashboard'

  return (
    <div className="app">
      <nav className="sidebar">
        <div className="sidebar-brand">
          <span className="brand-icon">🧠</span>
          <span className="brand-text">GenAI Tracker</span>
        </div>
        <ul className="nav-list">
          {TABS.map(t => (
            <li key={t.id}>
              <button
                className={`nav-item${tab === t.id ? ' active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                <span className="nav-icon">{t.icon}</span>
                {t.label}
              </button>
            </li>
          ))}
        </ul>
        <div className="sidebar-footer">
          <button className="btn-ghost" onClick={actions.exportMarkdown}>↓ Export Markdown</button>
          <button className="btn-ghost danger" onClick={actions.reset}>↺ Reset Progress</button>
        </div>
      </nav>
      <main className="main">
        <div className="workspace-header">
          <div>
            <p className="workspace-kicker">Portfolio Workspace</p>
            <h2>{activeTabLabel}</h2>
          </div>
          <div className={`sync-pill ${syncMeta.conflict ? 'conflict' : syncMeta.dirty ? 'pending' : 'ok'}`}>
            Sync: {syncStateText}
          </div>
        </div>

        {(syncNotice || syncMeta.dirty || syncMeta.conflict || syncMeta.error) && (
          <div className={`sync-banner ${syncMeta.conflict ? 'conflict' : 'info'}`}>
            <div>
              <strong>Sync:</strong> {syncStateText}
              {syncNotice ? ` - ${syncNotice}` : ''}
            </div>
            {syncMeta.conflict && (
              <div className="sync-actions">
                <button className="btn-ghost" onClick={keepLocalAndOverwriteBackend}>Use Local</button>
                <button className="btn-ghost" onClick={useBackendVersion}>Use Backend</button>
              </div>
            )}
            {!syncMeta.conflict && syncMeta.dirty && (
              <div className="sync-actions">
                <button className="btn-ghost" onClick={retrySync}>Retry Sync</button>
              </div>
            )}
          </div>
        )}
        <View data={data} actions={actions} />
      </main>
    </div>
  )
}
