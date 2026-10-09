import { useMemo, useState } from 'react'
import { PROJECT_COLORS, PROJECT_NAMES } from '../data.js'

function WeekRow({ week, actions }) {
  const [open, setOpen] = useState(false)
  const done  = week.tasks.filter(t => t.done).length
  const total = week.tasks.length
  const p     = total === 0 ? 0 : Math.round((done / total) * 100)
  const color = PROJECT_COLORS[week.project]
  const complete = p === 100

  return (
    <div className={`week-row${complete ? ' complete' : ''}`}>
      <div className="week-header" onClick={() => setOpen(!open)}>
        <div className="week-header-left">
          <span className="week-num" style={{ background: color }}>W{week.week}</span>
          <div>
            <span className="week-focus">{week.focus}</span>
            <span className="week-project-tag" style={{ color }}>{PROJECT_NAMES[week.project]}</span>
          </div>
        </div>
        <div className="week-header-right">
          <div className="mini-bar">
            <div style={{ width: `${p}%`, background: color, height: '100%', borderRadius: '3px', transition: 'width 0.3s' }} />
          </div>
          <span className="week-count">{done}/{total}</span>
          {complete && <span className="week-tick">OK</span>}
          <span className="chevron">{open ? '[-]' : '[+]'}</span>
        </div>
      </div>

      {open && (
        <div className="week-body">
          <ul className="task-list">
            {week.tasks.map(t => (
              <li key={t.id} className={`task-item${t.done ? ' done' : ''}`}>
                <label>
                  <input
                    type="checkbox"
                    checked={t.done}
                    onChange={() => actions.toggleTask(week.week, t.id)}
                  />
                  <span>{t.label}</span>
                </label>
              </li>
            ))}
          </ul>
          <textarea
            className="week-notes"
            rows={2}
            value={week.notes}
            onChange={e => actions.setWeekNotes(week.week, e.target.value)}
            placeholder="Week notes, blockers, decisions..."
          />
        </div>
      )}
    </div>
  )
}

export default function Weekly({ data, actions }) {
  const [projectFilter, setProjectFilter] = useState('all')
  const [incompleteOnly, setIncompleteOnly] = useState(false)

  const visibleWeeks = useMemo(() => {
    return data.weeks.filter(week => {
      const matchesProject = projectFilter === 'all' ? true : String(week.project) === projectFilter
      if (!matchesProject) return false
      if (!incompleteOnly) return true
      return (week.tasks || []).some(task => !task.done)
    })
  }, [data.weeks, projectFilter, incompleteOnly])

  const totalT = data.weeks.reduce((s, w) => s + w.tasks.length, 0)
  const doneT  = data.weeks.reduce((s, w) => s + w.tasks.filter(t => t.done).length, 0)
  return (
    <div className="view">
      <h1>Weekly Tracker</h1>
      <p className="view-sub">{doneT}/{totalT} tasks complete | 14 weeks</p>

      <div className="weekly-toolbar">
        <select className="status-select" value={projectFilter} onChange={e => setProjectFilter(e.target.value)}>
          <option value="all">All projects</option>
          {Object.entries(PROJECT_NAMES).map(([projectId, name]) => (
            <option key={projectId} value={projectId}>{name}</option>
          ))}
        </select>
        <label className="weekly-toggle">
          <input type="checkbox" checked={incompleteOnly} onChange={e => setIncompleteOnly(e.target.checked)} />
          Show only weeks with incomplete tasks
        </label>
      </div>

      <div className="weeks-list">
        {visibleWeeks.map(w => (
          <WeekRow key={w.week} week={w} actions={actions} />
        ))}
        {visibleWeeks.length === 0 && <div className="empty-state">No weeks match the selected filters.</div>}
      </div>
    </div>
  )
}
