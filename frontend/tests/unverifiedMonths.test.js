import test from 'node:test'
import assert from 'node:assert/strict'

import { describeUnverifiedMonths } from '../src/components/dashboard/format.js'

function point(month, status) {
  return { month, status, from_date: '2025-11-01' }
}

test('names a single unreadable month', () => {
  const series = [
    point('Nov 2025', 'unverified'),
    point('Dec 2025', 'available'),
  ]

  assert.equal(describeUnverifiedMonths(series), 'Nov 2025')
})

test('joins two unreadable months with "and"', () => {
  const series = [
    point('Nov 2025', 'unverified'),
    point('Dec 2025', 'available'),
    point('Feb 2026', 'unverified'),
  ]

  assert.equal(describeUnverifiedMonths(series), 'Nov 2025 and Feb 2026')
})

test('lists three or more with commas and a final "and"', () => {
  const series = [
    point('Nov 2025', 'unverified'),
    point('Feb 2026', 'unverified'),
    point('Apr 2026', 'unverified'),
  ]

  assert.equal(
    describeUnverifiedMonths(series),
    'Nov 2025, Feb 2026 and Apr 2026'
  )
})

test('returns an empty string when every month was readable', () => {
  const series = [
    point('Dec 2025', 'available'),
    point('Jan 2026', 'no_entries'),
  ]

  assert.equal(describeUnverifiedMonths(series), '')
})

test('handles a missing or empty series', () => {
  assert.equal(describeUnverifiedMonths([]), '')
  assert.equal(describeUnverifiedMonths(undefined), '')
  assert.equal(describeUnverifiedMonths(null), '')
})
