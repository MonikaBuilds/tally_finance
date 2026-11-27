import test from 'node:test'
import assert from 'node:assert/strict'

import { reportPathWithPeriod } from '../src/utils/dashboardDateFilter.js'

test('carries the selected period into the report link', () => {
  const path = reportPathWithPeriod('/reports/profit-loss', {
    fromDate: '2025-04-01',
    toDate: '2025-06-30',
  })

  assert.equal(
    path,
    '/reports/profit-loss?from_date=2025-04-01&to_date=2025-06-30'
  )
})

test('a custom range is never dropped in favour of the default period', () => {
  const path = reportPathWithPeriod('/reports/profit-loss', {
    fromDate: '2026-01-01',
    toDate: '2026-01-31',
  })

  assert.ok(path.includes('from_date=2026-01-01'))
  assert.ok(path.includes('to_date=2026-01-31'))
})

test('works for every report a KPI can open', () => {
  const filter = { fromDate: '2025-04-01', toDate: '2026-03-31' }

  for (const base of [
    '/reports/profit-loss',
    '/reports/balance-sheet',
    '/reports/trial-balance',
  ]) {
    const path = reportPathWithPeriod(base, filter)

    assert.ok(path.startsWith(`${base}?`), `${base} lost its query string`)
    assert.ok(path.includes('from_date=2025-04-01'))
    assert.ok(path.includes('to_date=2026-03-31'))
  }
})

test('falls back to the bare path when no period is known', () => {
  assert.equal(
    reportPathWithPeriod('/reports/profit-loss', {}),
    '/reports/profit-loss'
  )
  assert.equal(
    reportPathWithPeriod('/reports/profit-loss', null),
    '/reports/profit-loss'
  )
  assert.equal(
    reportPathWithPeriod('/reports/profit-loss', { fromDate: '2026-01-01' }),
    '/reports/profit-loss'
  )
})
