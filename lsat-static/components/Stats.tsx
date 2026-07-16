'use client'

import { useEffect, useState } from 'react'
import { SECTIONS, sectionMeta } from '@/lib/data'
import {
  type Attempt,
  clearAttempts,
  getAttempts,
  overallAccuracy,
  sectionAccuracy,
} from '@/lib/progress'

/** All-time + per-section accuracy from localStorage, with a guarded reset. */
export default function Stats() {
  const [attempts, setAttempts] = useState<Attempt[]>([])

  useEffect(() => {
    setAttempts(getAttempts())
  }, [])

  const overall = overallAccuracy(attempts)

  function reset() {
    if (!window.confirm('Erase all saved practice history on this device? This cannot be undone.')) {
      return
    }
    clearAttempts()
    setAttempts([])
  }

  return (
    <section aria-label="Statistics">
      <div className="drill-head">
        <h2>Your progress</h2>
        <p className="drill-timing">Stored only in this browser</p>
      </div>

      {overall.attempted === 0 ? (
        <p className="empty">No attempts yet — start a drill to build your stats.</p>
      ) : (
        <>
          <div className="stat-hero">
            <div className="stat-num">{overall.pct}%</div>
            <div className="stat-sub">
              {overall.correct} / {overall.attempted} questions correct
            </div>
          </div>

          <table className="stat-table">
            <thead>
              <tr>
                <th scope="col">Section</th>
                <th scope="col">Correct</th>
                <th scope="col">Attempted</th>
                <th scope="col">Accuracy</th>
              </tr>
            </thead>
            <tbody>
              {SECTIONS.map((code) => {
                const a = sectionAccuracy(attempts, code)
                return (
                  <tr key={code}>
                    <th scope="row">{sectionMeta(code)?.name ?? code}</th>
                    <td>{a.correct}</td>
                    <td>{a.attempted}</td>
                    <td>{a.attempted ? `${a.pct}%` : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          <button type="button" className="btn btn-danger" onClick={reset}>
            Reset progress
          </button>
        </>
      )}
    </section>
  )
}
