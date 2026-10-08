const LI_COLORS = { low: '#10b981', medium: '#f59e0b', high: '#ef4444' }
const ST_COLORS  = { open: '#ef4444', mitigated: '#f59e0b', closed: '#10b981' }
const LEVEL_SCORE = { low: 1, medium: 2, high: 3 }

export default function Risks({ data, actions }) {
  const open = data.risks.filter(r => r.status === 'open').length
  const highPriority = data.risks.filter(r => r.status === 'open' && (r.likelihood === 'high' || r.impact === 'high')).length
  const totalScore = data.risks.reduce((sum, r) => sum + (LEVEL_SCORE[r.likelihood] || 0) + (LEVEL_SCORE[r.impact] || 0), 0)
  const avgScore = data.risks.length ? (totalScore / data.risks.length).toFixed(1) : '0.0'
  return (
    <div className="view">
      <div className="view-header-row">
        <div>
          <h1>Risk Register</h1>
          <p className="view-sub">{open} open | {data.risks.length} total</p>
          <div className="risk-summary-row">
            <span className="risk-summary-chip">High-priority open: {highPriority}</span>
            <span className="risk-summary-chip">Average severity score: {avgScore}</span>
          </div>
        </div>
        <button className="btn-primary" onClick={actions.addRisk}>+ Add Risk</button>
      </div>

      <div className="card">
        {data.risks.length === 0
          ? <p className="empty-state">No risks logged yet - click "Add Risk" to start.</p>
          : (
            <div className="risk-table-wrap">
              <table className="risk-table">
                <thead>
                  <tr>
                    <th style={{ width: '30%' }}>Description</th>
                    <th>Likelihood</th>
                    <th>Impact</th>
                    <th>Score</th>
                    <th style={{ width: '30%' }}>Mitigation</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {data.risks.map(r => (
                    <tr key={r.id}>
                      <td>
                        <input
                          className="risk-input"
                          value={r.description}
                          onChange={e => actions.updateRisk(r.id, 'description', e.target.value)}
                          placeholder="Describe the riskΓÇª"
                        />
                      </td>
                      <td>
                        <select
                          className="risk-select"
                          style={{ color: LI_COLORS[r.likelihood] }}
                          value={r.likelihood}
                          onChange={e => actions.updateRisk(r.id, 'likelihood', e.target.value)}
                        >
                          <option value="low">Low</option>
                          <option value="medium">Medium</option>
                          <option value="high">High</option>
                        </select>
                      </td>
                      <td>
                        <select
                          className="risk-select"
                          style={{ color: LI_COLORS[r.impact] }}
                          value={r.impact}
                          onChange={e => actions.updateRisk(r.id, 'impact', e.target.value)}
                        >
                          <option value="low">Low</option>
                          <option value="medium">Medium</option>
                          <option value="high">High</option>
                        </select>
                      </td>
                      <td>
                        <span className="risk-score-pill">
                          {(LEVEL_SCORE[r.likelihood] || 0) + (LEVEL_SCORE[r.impact] || 0)}
                        </span>
                      </td>
                      <td>
                        <input
                          className="risk-input"
                          value={r.mitigation}
                          onChange={e => actions.updateRisk(r.id, 'mitigation', e.target.value)}
                          placeholder="Mitigation strategy..."
                        />
                      </td>
                      <td>
                        <select
                          className="risk-select"
                          style={{ color: ST_COLORS[r.status], fontWeight: 600 }}
                          value={r.status}
                          onChange={e => actions.updateRisk(r.id, 'status', e.target.value)}
                        >
                          <option value="open">Open</option>
                          <option value="mitigated">Mitigated</option>
                          <option value="closed">Closed</option>
                        </select>
                      </td>
                      <td>
                        <button
                          className="btn-icon danger"
                          title="Delete risk"
                          onClick={() => actions.deleteRisk(r.id)}
                        >x</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </div>
    </div>
  )
}
