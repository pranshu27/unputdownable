import { useState } from 'react'

const CATS = ['Problem Solving', 'Debugging', 'Architecture', 'Delivery', 'Leadership', 'Collaboration', 'Learning']
const MOODS = ['🟢', '🟡', '🔴', '⚪']

const STAR_PRESSURE_WORDS = /(unexpected|blocker|tradeoff|trade-off|deadline|failed|failure|bug|risk|incident|under pressure|pivot|outage|silently|conflict)/i
const STAR_NUMERIC_WORDS = /(\d|%|percent|hours?|days?|weeks?|months?|seconds?|minutes?|ms|x|kpi|sla|p\d{2}|latency|uptime)/i
const STAR_LEARNING_WORDS = /(learned|learnt|would do differently|next time|taught me|lesson|in hindsight)/i

function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 5) }
function todayStr() { return new Date().toISOString().slice(0, 10) }

function wc(text = '') {
  return text.trim() ? text.trim().split(/\s+/).length : 0
}

function scoreStarChecklist(story = {}) {
  const sWords = wc(story.situation || '')
  const tWords = wc(story.task || '')
  const aWords = wc(story.action || '')
  const rWords = wc(story.result || '')

  const checks = [
    {
      id: 's-brief',
      label: 'Situation is relevant and brief (2-3 key details)',
      pass: sWords >= 12 && sWords <= 90
    },
    {
      id: 't-brief',
      label: 'Task is concise (1-2 main responsibility points)',
      pass: tWords >= 8 && tWords <= 55
    },
    {
      id: 'a-depth',
      label: 'Action is the most detailed section and focuses on your contribution',
      pass: aWords > sWords && aWords > tWords && aWords > rWords && /\bI\b/i.test(story.action || '')
    },
    {
      id: 'r-concrete',
      label: 'Result includes at least one concrete outcome',
      pass: STAR_NUMERIC_WORDS.test(story.result || '')
    },
    {
      id: 'r-learning',
      label: 'Result includes what you learned',
      pass: STAR_LEARNING_WORDS.test(story.result || '')
    },
    {
      id: 'real-signal',
      label: 'Story shows a real challenge, pressure, or tradeoff',
      pass: STAR_PRESSURE_WORDS.test(`${story.situation || ''} ${story.action || ''}`)
    }
  ]

  const passed = checks.filter(c => c.pass).length
  return { checks, passed, total: checks.length, ready: passed === checks.length }
}

// ─── Inline editable field ─────────────────────────────────────────────────
function Field({ label, value, onChange, multiline = false, rows = 3, placeholder = '' }) {
  return (
    <div className="jrn-field">
      <div className="jrn-label">{label}</div>
      {multiline
        ? <textarea className="jrn-input" rows={rows} value={value} placeholder={placeholder}
            onChange={e => onChange(e.target.value)} />
        : <input className="jrn-input" value={value} placeholder={placeholder}
            onChange={e => onChange(e.target.value)} />}
    </div>
  )
}

// ─── Daily Entry Card ──────────────────────────────────────────────────────
function DailyCard({ entry, actions }) {
  const [open, setOpen] = useState(entry._new || false)

  const upd = (field, val) => actions.updateDailyEntry(entry.id, field, val)
  const winsArr = entry.wins || []
  const lossArr = entry.losses || []

  return (
    <div className={`jrn-card${open ? ' open' : ''}`}>
      <div className="jrn-card-header" onClick={() => setOpen(!open)}>
        <div className="jrn-card-left">
          <span className="jrn-mood">{entry.mood || '⚪'}</span>
          <div>
            <div className="jrn-card-title">
              {entry.title || <em style={{ opacity: 0.4 }}>Untitled session</em>}
            </div>
            <div className="jrn-card-meta">{entry.date}</div>
          </div>
        </div>
        <div className="jrn-card-right">
          <span className="jrn-pill win">{winsArr.length}W</span>
          <span className="jrn-pill loss">{lossArr.length}L</span>
          <button className="jrn-del" onClick={e => { e.stopPropagation(); actions.deleteDailyEntry(entry.id) }}>✕</button>
          <span className="jrn-chevron">{open ? '▲' : '▼'}</span>
        </div>
      </div>

      {open && (
        <div className="jrn-card-body" onClick={e => e.stopPropagation()}>
          <div className="jrn-row">
            <div className="jrn-field">
              <div className="jrn-label">Date</div>
              <input className="jrn-input" type="date" value={entry.date} onChange={e => upd('date', e.target.value)} />
            </div>
            <div className="jrn-field">
              <div className="jrn-label">Mood</div>
              <div className="jrn-mood-row">
                {MOODS.map(m => (
                  <button key={m} className={`jrn-mood-btn${entry.mood === m ? ' sel' : ''}`}
                    onClick={() => upd('mood', m)}>{m}</button>
                ))}
              </div>
            </div>
            <div className="jrn-field">
              <div className="jrn-label">Energy</div>
              <div className="jrn-energy-row">
                {[1,2,3,4,5].map(n => (
                  <button key={n} className={`jrn-energy-btn${(entry.energy||0) >= n ? ' sel' : ''}`}
                    onClick={() => upd('energy', n)}>●</button>
                ))}
              </div>
            </div>
          </div>

          <Field label="Session Title" value={entry.title || ''} onChange={v => upd('title', v)}
            placeholder="e.g. RAG W1 — embeddings upgrade" />

          <div className="jrn-wins-losses">
            <div className="jrn-col">
              <div className="jrn-label" style={{ color: 'var(--jrn-green)' }}>✅ Wins</div>
              {winsArr.map((w, i) => (
                <div key={i} className="jrn-list-item">
                  <input className="jrn-input" value={w} placeholder="What went well?"
                    onChange={e => {
                      const next = [...winsArr]; next[i] = e.target.value; upd('wins', next)
                    }} />
                  <button className="jrn-del small" onClick={() => upd('wins', winsArr.filter((_,j)=>j!==i))}>✕</button>
                </div>
              ))}
              <button className="jrn-add-item" onClick={() => upd('wins', [...winsArr, ''])}>+ win</button>
            </div>
            <div className="jrn-col">
              <div className="jrn-label" style={{ color: 'var(--jrn-red)' }}>🔴 Blockers</div>
              {lossArr.map((l, i) => (
                <div key={i} className="jrn-list-item">
                  <input className="jrn-input" value={l} placeholder="What blocked you?"
                    onChange={e => {
                      const next = [...lossArr]; next[i] = e.target.value; upd('losses', next)
                    }} />
                  <button className="jrn-del small" onClick={() => upd('losses', lossArr.filter((_,j)=>j!==i))}>✕</button>
                </div>
              ))}
              <button className="jrn-add-item" onClick={() => upd('losses', [...lossArr, ''])}>+ blocker</button>
            </div>
          </div>

          <Field label="Notes / Reflection" value={entry.notes || ''} onChange={v => upd('notes', v)}
            multiline rows={2} placeholder="What would you do differently?" />
        </div>
      )}
    </div>
  )
}

// ─── STAR Card ─────────────────────────────────────────────────────────────
function StarCard({ story, actions, checklist }) {
  const [open, setOpen] = useState(story._new || false)
  const upd = (field, val) => actions.updateStarStory(story.id, field, val)

  return (
    <div className={`jrn-card${open ? ' open' : ''}`}>
      <div className="jrn-card-header" onClick={() => setOpen(!open)}>
        <div className="jrn-card-left">
          <span className="jrn-star-icon">⭐</span>
          <div>
            <div className="jrn-card-title">
              {story.title || <em style={{ opacity: 0.4 }}>Untitled story</em>}
            </div>
            <div className="jrn-card-meta">
              <span className="jrn-cat-tag">{story.category || 'General'}</span>
              <span>{story.date}</span>
              <span className={`jrn-check-pill${checklist.ready ? ' pass' : ' warn'}`}>
                Checklist {checklist.passed}/{checklist.total}
              </span>
            </div>
          </div>
        </div>
        <div className="jrn-card-right">
          <button className="jrn-del" onClick={e => { e.stopPropagation(); actions.deleteStarStory(story.id) }}>✕</button>
          <span className="jrn-chevron">{open ? '▲' : '▼'}</span>
        </div>
      </div>

      {open && (
        <div className="jrn-card-body" onClick={e => e.stopPropagation()}>
          <div className="jrn-row">
            <Field label="Story Title" value={story.title || ''} onChange={v => upd('title', v)}
              placeholder="e.g. Fixed race condition in ingest pipeline" />
            <div className="jrn-field">
              <div className="jrn-label">Category</div>
              <select className="jrn-input jrn-select" value={story.category || 'Problem Solving'}
                onChange={e => upd('category', e.target.value)}>
                {CATS.map(c => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div className="jrn-field">
              <div className="jrn-label">Date</div>
              <input className="jrn-input" type="date" value={story.date}
                onChange={e => upd('date', e.target.value)} />
            </div>
          </div>

          <div className="jrn-star-grid">
            {[
              ['S — Situation', 'situation', 'What was the context? What problem existed?'],
              ['T — Task',      'task',      'What was YOUR specific responsibility?'],
              ['A — Action',    'action',    'What did you do? Be specific about your decisions.'],
              ['R — Result',    'result',    'What was the measurable outcome?'],
            ].map(([lbl, key, ph]) => (
              <div key={key} className="jrn-star-row">
                <div className="jrn-star-letter">{lbl.slice(0,1)}</div>
                <div className="jrn-field" style={{ flex: 1 }}>
                  <div className="jrn-label">{lbl}</div>
                  <textarea className="jrn-input" rows={3} value={story[key] || ''}
                    placeholder={ph} onChange={e => upd(key, e.target.value)} />
                </div>
              </div>
            ))}
          </div>

          <div className="jrn-checklist">
            <div className="jrn-label">STAR Quality Checklist</div>
            <div className="jrn-checklist-items">
              {checklist.checks.map(item => (
                <div key={item.id} className={`jrn-check-item${item.pass ? ' pass' : ' fail'}`}>
                  <span className="jrn-check-icon">{item.pass ? '✓' : '!'}</span>
                  <span>{item.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main Journal View ─────────────────────────────────────────────────────
export default function Journal({ data, actions }) {
  const [subtab, setSubtab] = useState('daily')
  const [search, setSearch] = useState('')
  const [readyOnly, setReadyOnly] = useState(false)

  const journal = data.journal || { daily: [], stories: [] }
  const daily   = [...(journal.daily || [])].sort((a,b) => b.date.localeCompare(a.date))
  const q       = search.toLowerCase()
  const stories = [...(journal.stories || [])]
    .filter(s => !q || s.title?.toLowerCase().includes(q) || s.situation?.toLowerCase().includes(q) || s.action?.toLowerCase().includes(q))
    .sort((a,b) => b.date.localeCompare(a.date))
  const storiesWithChecklist = stories.map(s => ({ story: s, checklist: scoreStarChecklist(s) }))
  const visibleStories = readyOnly
    ? storiesWithChecklist.filter(x => x.checklist.ready)
    : storiesWithChecklist

  const totalWins = daily.reduce((s,e) => s + (e.wins||[]).filter(Boolean).length, 0)
  const totalLoss = daily.reduce((s,e) => s + (e.losses||[]).filter(Boolean).length, 0)
  const readyStories = storiesWithChecklist.filter(x => x.checklist.ready).length

  return (
    <div className="view">
      <div className="jrn-header">
        <div>
          <h1>Journal</h1>
          <p className="view-sub">Daily log · STAR stories · {daily.length} sessions · {totalWins} wins · {totalLoss} blockers</p>
          <div className="journal-summary-row">
            <span className="journal-summary-chip">STAR-ready stories: {readyStories}/{storiesWithChecklist.length}</span>
            <span className="journal-summary-chip">Win/Blocker ratio: {totalLoss === 0 ? totalWins : (totalWins / totalLoss).toFixed(2)}</span>
          </div>
        </div>
        <button className="btn-primary"
          onClick={() => subtab === 'daily' ? actions.addDailyEntry() : actions.addStarStory()}>
          {subtab === 'daily' ? '+ New Entry' : '+ New Story'}
        </button>
      </div>

      <div className="jrn-tabs">
        <button className={`jrn-tab${subtab==='daily'?' active':''}`} onClick={() => setSubtab('daily')}>
          📅 Daily Log ({daily.length})
        </button>
        <button className={`jrn-tab${subtab==='stories'?' active':''}`} onClick={() => setSubtab('stories')}>
          ⭐ STAR Stories ({journal.stories?.length || 0})
        </button>
      </div>

      {subtab === 'stories' && (
        <>
          <input className="jrn-search" placeholder="Search stories…" value={search}
            onChange={e => setSearch(e.target.value)} />
          <label className="journal-toggle-ready">
            <input type="checkbox" checked={readyOnly} onChange={e => setReadyOnly(e.target.checked)} />
            Show only STAR-ready stories
          </label>
          <div className="jrn-check-summary">
            STAR-ready stories: {readyStories}/{storiesWithChecklist.length}
          </div>
        </>
      )}

      <div className="jrn-list">
        {subtab === 'daily' && (
          daily.length === 0
            ? <div className="empty-state">No entries yet. Click "+ New Entry" to start.</div>
            : daily.map(e => <DailyCard key={e.id} entry={e} actions={actions} />)
        )}
        {subtab === 'stories' && (
          visibleStories.length === 0
            ? <div className="empty-state">{search ? `No stories matching "${search}"` : 'No stories yet. Click "+ New Story".'}</div>
            : visibleStories.map(({ story, checklist }) => (
              <StarCard key={story.id} story={story} actions={actions} checklist={checklist} />
            ))
        )}
      </div>
    </div>
  )
}
