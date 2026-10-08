import { STATUSES } from '../data.js'

function pct(done, total) {
  return total === 0 ? 0 : Math.round((done / total) * 100)
}

function StatCard({ value, label, sub, color }) {
  return (
    <div className="stat-card">
      <div className="stat-value" style={{ color }}>{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

function nextMilestone(project) {
  return (project.milestones || []).find(m => !m.done)?.label || 'All milestones complete'
}

function ProjectRow({ project }) {
  const done  = project.milestones.filter(m => m.done).length
  const total = project.milestones.length
  const p     = pct(done, total)
  const s     = STATUSES[project.status]
  return (
    <div className="project-row">
      <div className="project-row-bar-color" style={{ background: project.color }} />
      <div className="project-row-info">
        <span className="project-row-name">P{project.id}: {project.name}</span>
        <span className="project-row-range">{project.weekRange}</span>
      </div>
      <div className="project-row-badge">
        <span className="badge" style={{ background: s.color + '22', color: s.color }}>{s.label}</span>
      </div>
      <div className="project-row-progress">
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${p}%`, background: project.color }} />
        </div>
        <span className="progress-label">{done}/{total}</span>
      </div>
    </div>
  )
}

export default function Dashboard({ data, actions }) {
  const totalM  = data.projects.reduce((s, p) => s + p.milestones.length, 0)
  const doneM   = data.projects.reduce((s, p) => s + p.milestones.filter(m => m.done).length, 0)
  const totalT  = data.weeks.reduce((s, w) => s + w.tasks.length, 0)
  const doneT   = data.weeks.reduce((s, w) => s + w.tasks.filter(t => t.done).length, 0)
  const doneP   = data.projects.filter(p => p.status === 'done').length
  const inProg  = data.projects.filter(p => p.status === 'in-progress').length
  const openR   = data.risks.filter(r => r.status === 'open').length
  const highRisks = data.risks.filter(r => r.status === 'open' && (r.likelihood === 'high' || r.impact === 'high')).length
  const p1 = data.projects.find(p => p.id === 1)
  const p1Done = p1 ? p1.milestones.filter(m => m.done).length : 0
  const p1Total = p1 ? p1.milestones.length : 0

  return (
    <div className="view">
      <h1>Program Dashboard</h1>
      <p className="view-sub">{data.program.name} | {data.program.owner}</p>

      <div className="stats-row">
        <StatCard value={`${pct(doneM, totalM)}%`}  label="Milestone Progress"  sub={`${doneM}/${totalM} done`}         color="#6366f1" />
        <StatCard value={`${pct(doneT, totalT)}%`}  label="Weekly Tasks"        sub={`${doneT}/${totalT} done`}         color="#0ea5e9" />
        <StatCard value={doneP}                      label="Projects Done"       sub={`${inProg} in progress`}           color="#10b981" />
        <StatCard value={openR}                      label="Open Risks"          sub={`${data.risks.length} total`}      color="#f59e0b" />
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Overall Program Progress</h3>
          <span className="pct-badge">{pct(doneM, totalM)}%</span>
        </div>
        <div className="progress-track large">
          <div className="progress-fill gradient" style={{ width: `${pct(doneM, totalM)}%` }} />
        </div>
      </div>

      <div className="card">
        <h3>Delivery Signals</h3>
        <div className="signal-grid">
          <div className="signal-card">
            <span>Lineage Engine</span>
            <strong>Semantic + NetworkX</strong>
            <small>Cross-workflow trace enabled for anchored field queries.</small>
          </div>
          <div className="signal-card">
            <span>P1 Completion</span>
            <strong>{p1Done}/{p1Total} milestones</strong>
            <small>Deterministic lineage/impact route is active in semantic-primary mode.</small>
          </div>
          <div className="signal-card">
            <span>Risk Heat</span>
            <strong>{highRisks} high-priority open risk(s)</strong>
            <small>{openR} open total across roadmap.</small>
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Program Metadata</h3>
        <div className="meta-grid">
          {[
            ['Program Name', 'name', 'text'],
            ['Owner',        'owner', 'text'],
            ['Tech Lead',    'techLead', 'text'],
            ['Start Date',   'startDate', 'date'],
            ['End Date',     'endDate', 'date']
          ].map(([label, field, type]) => (
            <label key={field} className="meta-field">
              <span>{label}</span>
              <input
                type={type}
                value={data.program[field]}
                onChange={e => actions.updateProgram(field, e.target.value)}
              />
            </label>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>Projects at a Glance</h3>
        <p className="view-sub" style={{ marginBottom: 10 }}>
          Next action focus: {data.projects.map(p => `P${p.id} ${nextMilestone(p)}`).slice(0, 2).join(' | ')}
        </p>
        <div className="projects-glance">
          {data.projects.map(p => <ProjectRow key={p.id} project={p} />)}
        </div>
      </div>
    </div>
  )
}
