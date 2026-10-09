import { useEffect, useMemo, useRef, useState } from 'react'
import { STATUSES } from '../data.js'

const API = 'http://localhost:8001'

function pct(done, total) {
  return total === 0 ? 0 : Math.round((done / total) * 100)
}

async function fetchProjectLld(projectId) {
  const r = await fetch(`${API}/api/project-lld/${projectId}`)
  const payload = await r.json().catch(() => ({}))
  if (!r.ok) {
    throw new Error(payload?.detail || `Failed to load LLD (HTTP ${r.status})`)
  }
  return payload
}

function isoToLocal(value) {
  if (!value) return 'unknown'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? 'unknown' : d.toLocaleString()
}

function renderMarkdown(content) {
  const parser = typeof window !== 'undefined' ? window.marked : null
  if (!parser || !content) {
    return null
  }
  return parser.parse(content)
}

async function ensureMermaid() {
  if (typeof window === 'undefined') return null
  if (window.mermaid) return window.mermaid
  if (window.__mermaidLoaderPromise) return window.__mermaidLoaderPromise

  window.__mermaidLoaderPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-mermaid-loader="tracker-lld"]')
    if (existing) {
      existing.addEventListener('load', () => resolve(window.mermaid || null), { once: true })
      existing.addEventListener('error', () => reject(new Error('Failed to load Mermaid runtime')), { once: true })
      return
    }

    const script = document.createElement('script')
    script.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js'
    script.async = true
    script.dataset.mermaidLoader = 'tracker-lld'
    script.onload = () => resolve(window.mermaid || null)
    script.onerror = () => reject(new Error('Failed to load Mermaid runtime'))
    document.head.appendChild(script)
  })

  return window.__mermaidLoaderPromise
}

function materializeMermaidNodes(root) {
  if (!root) return []
  const codeNodes = root.querySelectorAll('pre code.language-mermaid, pre code.lang-mermaid')
  codeNodes.forEach((codeNode) => {
    const pre = codeNode.closest('pre')
    if (!pre || !pre.parentNode) return

    const container = document.createElement('div')
    container.className = 'mermaid'
    container.textContent = codeNode.textContent || ''
    pre.parentNode.replaceChild(container, pre)
  })

  return Array.from(root.querySelectorAll('.mermaid'))
}

function ProjectCard({ project, actions }) {
  const [open, setOpen] = useState(false)
  const [lldOpen, setLldOpen] = useState(false)
  const [lldFullscreen, setLldFullscreen] = useState(false)
  const [lldLoading, setLldLoading] = useState(false)
  const [lldError, setLldError] = useState('')
  const [lldDoc, setLldDoc] = useState(null)
  const lldPanelRef = useRef(null)
  const lldFullscreenRef = useRef(null)
  const done  = project.milestones.filter(m => m.done).length
  const total = project.milestones.length
  const openCount = Math.max(total - done, 0)
  const p     = pct(done, total)
  const s     = STATUSES[project.status]

  const loadLld = async (force = false) => {
    if (lldLoading) return
    if (!force && lldDoc && !lldError) return

    setLldLoading(true)
    setLldError('')
    try {
      const doc = await fetchProjectLld(project.id)
      setLldDoc(doc)
    } catch (err) {
      setLldError(err?.message || 'Unable to load LLD document')
    } finally {
      setLldLoading(false)
    }
  }

  const toggleLld = async () => {
    const next = !lldOpen
    setLldOpen(next)
    if (!next) {
      setLldFullscreen(false)
    }
    if (next) {
      await loadLld(false)
    }
  }

  const openFullscreen = async () => {
    if (!lldOpen) {
      setLldOpen(true)
      await loadLld(false)
    }
    setLldFullscreen(true)
  }

  const closeFullscreen = () => setLldFullscreen(false)

  useEffect(() => {
    if (!lldFullscreen) return undefined

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        closeFullscreen()
      }
    }

    const oldOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKeyDown)

    return () => {
      document.body.style.overflow = oldOverflow
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [lldFullscreen])

  useEffect(() => {
    const run = async () => {
      if (!lldDoc?.content || lldError) return

      const mermaid = await ensureMermaid().catch(() => null)
      if (!mermaid) return

      if (!window.__trackerMermaidInitialized) {
        mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose' })
        window.__trackerMermaidInitialized = true
      }

      const roots = [lldPanelRef.current, lldFullscreenRef.current].filter(Boolean)
      for (const root of roots) {
        const nodes = materializeMermaidNodes(root)
        if (!nodes.length) continue
        try {
          await mermaid.run({ nodes })
        } catch (err) {
          console.warn('Mermaid render failed in LLD view', err)
        }
      }
    }

    run()
  }, [lldDoc?.content, lldError, lldOpen, lldFullscreen])

  const lldHtml = renderMarkdown(lldDoc?.content || '') || `<pre>${lldDoc?.content || ''}</pre>`

  return (
    <div className="project-card" style={{ '--project-color': project.color }}>
      <div className="project-card-header" onClick={() => setOpen(!open)}>
        <div className="project-card-left">
          <div className="project-num" style={{ background: project.color }}>P{project.id}</div>
          <div>
            <h3>{project.name}</h3>
            <span className="project-range">{project.weekRange}</span>
          </div>
        </div>
        <div className="project-card-right">
          <span className="badge" style={{ background: s.color + '22', color: s.color }}>{s.label}</span>
          <span className="chevron">{open ? '[-]' : '[+]'}</span>
        </div>
      </div>

      <div className="project-progress-row">
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${p}%`, background: project.color }} />
        </div>
        <span className="progress-label">{done}/{total} milestones</span>
      </div>

      <div className="project-chip-row">
        <span className="project-chip">Open milestones: {openCount}</span>
        <span className="project-chip">LLD linked: {project.lld?.path ? 'yes' : 'no'}</span>
        <span className="project-chip">Notes: {(project.notes || '').trim() ? 'updated' : 'empty'}</span>
      </div>

      {open && (
        <div className="project-card-body">
          <p className="project-desc">{project.description}</p>

          <div className="project-detail-grid">
            <div>
              <h4>Milestones</h4>
              <ul className="milestone-list">
                {project.milestones.map(m => (
                  <li key={m.id} className={`milestone-item${m.done ? ' done' : ''}`}>
                    <label>
                      <input
                        type="checkbox"
                        checked={m.done}
                        onChange={() => actions.toggleMilestone(project.id, m.id)}
                      />
                      <span>{m.label}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <h4>KPIs</h4>
              <ul className="kpi-list">
                {project.kpis.map((k, i) => <li key={i}>{k}</li>)}
              </ul>

              <h4>Stack</h4>
              <div className="stack-tags">
                {project.stack.map((s, i) => <span key={i} className="stack-tag">{s}</span>)}
              </div>

              <h4>Status</h4>
              <select
                className="status-select"
                value={project.status}
                style={{ borderColor: STATUSES[project.status].color, color: STATUSES[project.status].color }}
                onChange={e => actions.setProjectStatus(project.id, e.target.value)}
              >
                {Object.entries(STATUSES).map(([v, { label }]) => (
                  <option key={v} value={v}>{label}</option>
                ))}
              </select>

              <h4>LLD Document</h4>
              <div className="lld-actions">
                <button className="lld-btn" onClick={toggleLld}>
                  {lldOpen ? 'Hide LLD' : 'View LLD'}
                </button>
                {lldOpen && (
                  <button className="lld-btn secondary" onClick={() => loadLld(true)}>
                    Reload
                  </button>
                )}
                <button className="lld-btn secondary" onClick={openFullscreen}>
                  Full Screen
                </button>
              </div>
              {lldLoading && <p className="lld-meta">Loading LLD...</p>}
            </div>
          </div>

          {lldOpen && (
            <div className="lld-panel">
              <div className="lld-header">
                <strong>{lldDoc?.title || project.lld?.title || `P${project.id} LLD`}</strong>
                <span className="lld-meta">
                  Updated: {isoToLocal(lldDoc?.updated_at)}
                </span>
              </div>
              <div className="lld-meta">
                Source: {lldDoc?.path || project.lld?.path || 'not available'}
              </div>

              {lldError && <div className="lld-error">{lldError}</div>}
              {!lldError && lldDoc?.content && (
                <div
                  ref={lldPanelRef}
                  className="lld-content lld-markdown"
                  dangerouslySetInnerHTML={{ __html: lldHtml }}
                />
              )}
            </div>
          )}

          {lldFullscreen && (
            <div className="lld-fs-overlay" onClick={closeFullscreen}>
              <div className="lld-fs-modal" onClick={e => e.stopPropagation()}>
                <div className="lld-fs-header">
                  <div>
                    <strong>{lldDoc?.title || project.lld?.title || `P${project.id} LLD`}</strong>
                    <div className="lld-meta">Source: {lldDoc?.path || project.lld?.path || 'not available'}</div>
                    <div className="lld-meta">Updated: {isoToLocal(lldDoc?.updated_at)}</div>
                  </div>
                  <button className="lld-btn" onClick={closeFullscreen}>Close</button>
                </div>

                {lldError && <div className="lld-error">{lldError}</div>}
                {!lldError && lldDoc?.content && (
                  <div
                    ref={lldFullscreenRef}
                    className="lld-fs-content lld-markdown"
                    dangerouslySetInnerHTML={{ __html: lldHtml }}
                  />
                )}
              </div>
            </div>
          )}

          <div className="notes-section">
            <h4>Notes / Blockers</h4>
            <textarea
              rows={3}
              value={project.notes}
              onChange={e => actions.setProjectNotes(project.id, e.target.value)}
              placeholder="Add project notes, decisions, blockers..."
            />
          </div>
        </div>
      )}
    </div>
  )
}

export default function Projects({ data, actions }) {
  const [statusFilter, setStatusFilter] = useState('all')
  const [search, setSearch] = useState('')

  const totalM = data.projects.reduce((s, p) => s + p.milestones.length, 0)
  const doneM  = data.projects.reduce((s, p) => s + p.milestones.filter(m => m.done).length, 0)
  const filteredProjects = useMemo(() => {
    const q = search.trim().toLowerCase()
    return data.projects.filter(project => {
      const statusOk = statusFilter === 'all' ? true : project.status === statusFilter
      if (!statusOk) return false
      if (!q) return true
      const haystack = [
        project.name,
        project.description,
        project.weekRange,
        ...(project.stack || []),
        ...(project.kpis || []),
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(q)
    })
  }, [data.projects, statusFilter, search])

  return (
    <div className="view">
      <h1>Projects</h1>
      <p className="view-sub">5 projects | 14 weeks | {doneM}/{totalM} milestones done</p>

      <div className="projects-toolbar">
        <input
          className="projects-search"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search project name, KPI, stack..."
        />
        <select
          className="status-select"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
        >
          <option value="all">All statuses</option>
          {Object.entries(STATUSES).map(([value, meta]) => (
            <option key={value} value={value}>{meta.label}</option>
          ))}
        </select>
      </div>

      <div className="projects-grid">
        {filteredProjects.map(p => (
          <ProjectCard key={p.id} project={p} actions={actions} />
        ))}
        {filteredProjects.length === 0 && (
          <div className="empty-state">No projects match the current filters.</div>
        )}
      </div>
    </div>
  )
}
