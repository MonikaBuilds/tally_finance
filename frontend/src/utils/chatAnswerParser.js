/*
 * Turns the assistant's plain-text answers into structured blocks the
 * chat UI can render as headings, summary tiles, tables and lists.
 *
 * The backend formatter (backend/app/chatbot/formatter.py) writes answers
 * as newline-separated text in a handful of repeating shapes:
 *
 *   HDFC Bank Transactions (from Tally):          -> heading
 *   Opening Balance: ₹0                            -> stat tile
 *   Period: 2025-04-01 to 2026-03-31               -> meta line
 *   • 2025-04-01 | Receipt #4 | Bajaj | ₹20,000 Dr  -> table row
 *   - Sweeper Salary | Indirect Expenses           -> table row
 *   - TDS on Rent: ₹12,000                         -> table row (name, value)
 *   ... and 12 more transactions.                  -> "more" note on the table
 *
 * Anything that does not match is kept as a paragraph, so an answer is
 * never lost — at worst it renders as text, the way it did before.
 */

import { formatDate } from './format.js'

const BULLET = /^\s*(?:[•*●-]|\d{1,3}[.)])\s+(.*)$/
const MORE = /^\s*(?:\.{3}|…)\s*(?:and\s+)?(\d[\d,]*)\s+more\b.*$/i
const FROM_TALLY = /\s*\((?:from|via)\s+tally\)\s*/i

const DATE = /^(?:\d{4}-\d{2}-\d{2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}[- ][A-Za-z]{3}[- ]\d{2,4})$/
const MONEY = /^[-+]?\s*₹\s*-?[\d,]+(?:\.\d+)?$/
const PLAIN_NUMBER = /^[-+]?[\d,]+(?:\.\d+)?%?$/
const DR_CR = /^(-?\s*₹\s*-?[\d,]+(?:\.\d+)?)\s+(Dr|Cr)$/i
const VOUCHER = /^([A-Za-z][A-Za-z .&()/-]*?)\s+#\s*(\S.*)$/
const LABELLED_MONEY = /^([A-Za-z][A-Za-z .]{0,24}?):?\s+(-?₹.*)$/

// A short figure: "₹32,85,000", "₹1,200 Dr", "11", "+12.5%", "₹500 (4%)".
const STAT_VALUE = /^[-+]?\s*(?:₹\s*-?)?[\d,]+(?:\.\d+)?%?(?:\s*(?:Dr|Cr))?(?:\s*\([^)]*\))?$/i

export function parseAmount(text) {
  if (text === null || text === undefined) return null
  const cleaned = String(text).replace(/₹|,|\s|Dr|Cr/gi, '')
  if (!/^[-+]?\d+(?:\.\d+)?$/.test(cleaned)) return null
  return Number(cleaned)
}

export function formatRupees(value) {
  const fractional = Math.round(value * 100) % 100 !== 0
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: fractional ? 2 : 0,
    maximumFractionDigits: fractional ? 2 : 0,
  }).format(value)
}

function toSortableDate(text) {
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (iso) return text
  const dmy = text.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$/)
  if (dmy) return `${dmy[3]}-${dmy[2].padStart(2, '0')}-${dmy[1].padStart(2, '0')}`
  return text
}

function isHeading(line) {
  return (
    line.endsWith(':') &&
    line.length <= 90 &&
    !line.slice(0, -1).includes(': ')
  )
}

function splitKeyValue(line) {
  const match = line.match(/^([^:]{1,48}):\s+(.+)$/)
  if (!match) return null
  const label = match[1].trim()
  const value = match[2].trim()
  if (label.split(/\s+/).length > 6) return null
  if (value.length > 70) return null
  // A sentence that happens to contain a colon is not a key/value pair.
  if (/[.!?]$/.test(value) && value.split(/\s+/).length > 6) return null
  return { label, value }
}

function bulletCells(body) {
  let cells
  if (body.includes(' | ')) {
    cells = body.split(' | ').map((cell) => cell.trim())
    // "Cash: Debit ₹10 | Credit ₹0" -> name, "Debit ₹10", "Credit ₹0"
    const head = splitKeyValue(cells[0])
    if (head && !DATE.test(head.label)) {
      cells = [head.label, head.value, ...cells.slice(1)]
    }
    return cells
  }

  const kv = splitKeyValue(body)
  if (kv) return [kv.label, kv.value]

  // "1. 2025-04-01 - Payment #3 - ₹15,000 Cr"
  const dashed = body.split(' - ').map((cell) => cell.trim())
  if (dashed.length >= 3 && dashed.some((cell) => MONEY.test(cell) || DR_CR.test(cell))) {
    return dashed
  }

  return null
}

function classifyColumn(values) {
  const present = values.filter((value) => value !== '' && value !== '-')
  if (present.length === 0) return { kind: 'text' }

  const all = (regex) => present.every((value) => regex.test(value))

  if (all(DATE)) return { kind: 'date' }
  if (all(DR_CR)) return { kind: 'drcr' }
  if (all(MONEY)) return { kind: 'money' }
  if (all(PLAIN_NUMBER)) return { kind: 'number' }
  if (all(VOUCHER)) return { kind: 'voucher' }

  const labelled = present.map((value) => value.match(LABELLED_MONEY))
  if (labelled.every(Boolean)) {
    const labels = new Set(labelled.map((match) => match[1].trim()))
    if (labels.size === 1) {
      const inner = labelled.map((match) => match[2].trim())
      const innerKind = inner.every((value) => DR_CR.test(value)) ? 'drcr' : 'money'
      return { kind: innerKind, label: [...labels][0], unwrap: LABELLED_MONEY }
    }
  }

  return { kind: 'text' }
}

function textColumnLabel(index, context) {
  if (index === 0) {
    if (context.isLedgerList) return 'Ledger'
    return context.hasDate ? 'Particulars' : 'Name'
  }
  if (index === 1) {
    if (context.isLedgerList) return 'Group'
    if (context.hasMoney) return context.hasDate ? 'Narration' : 'Details'
  }
  return 'Details'
}

function cell(display, sort = display) {
  return { display, sort }
}

function buildTable(items, heading, more) {
  const width = items[0].length
  const columnValues = Array.from({ length: width }, (_, col) =>
    items.map((row) => row[col] ?? ''),
  )
  const kinds = columnValues.map(classifyColumn)

  const context = {
    hasDate: kinds.some((kind) => kind.kind === 'date'),
    hasMoney: kinds.some((kind) => ['money', 'drcr'].includes(kind.kind)),
    isLedgerList: /ledger/i.test(heading || '') && width === 2 &&
      kinds.every((kind) => kind.kind === 'text'),
  }

  const columns = []
  const builders = []
  let textIndex = 0

  kinds.forEach((info, col) => {
    const unwrap = (raw) => {
      if (!info.unwrap) return raw
      const match = raw.match(info.unwrap)
      return match ? match[2].trim() : raw
    }

    switch (info.kind) {
      case 'date':
        columns.push({ label: 'Date', align: 'left', kind: 'date' })
        builders.push((row) => [cell(formatDate(row[col]), toSortableDate(row[col]))])
        break
      case 'voucher':
        columns.push({ label: 'Vch Type', align: 'left', kind: 'text' })
        columns.push({ label: 'Vch No.', align: 'left', kind: 'text' })
        builders.push((row) => {
          const match = row[col].match(VOUCHER)
          if (!match) return [cell(row[col]), cell('')]
          const number = match[2].trim()
          return [cell(match[1].trim()), cell(number, Number(number) || number)]
        })
        break
      case 'drcr':
        columns.push({ label: 'Debit', align: 'right', kind: 'money' })
        columns.push({ label: 'Credit', align: 'right', kind: 'money' })
        builders.push((row) => {
          const match = unwrap(row[col]).match(DR_CR)
          if (!match) return [cell(''), cell('')]
          const amount = parseAmount(match[1])
          const isDebit = match[2].toLowerCase() === 'dr'
          const filled = cell(match[1].replace(/\s+/g, ''), amount)
          const empty = cell('', null)
          return isDebit ? [filled, empty] : [empty, filled]
        })
        break
      case 'money':
      case 'number': {
        const label = info.label ||
          (info.kind === 'money' ? 'Amount' : width === 2 ? 'Value' : 'Count')
        columns.push({ label, align: 'right', kind: info.kind })
        builders.push((row) => {
          const raw = unwrap(row[col])
          return [cell(raw, parseAmount(raw))]
        })
        break
      }
      default: {
        const looksOverdue = columnValues[col].every((value) => /overdue/i.test(value))
        columns.push({
          label: looksOverdue ? 'Overdue' : textColumnLabel(textIndex, context),
          align: 'left',
          kind: 'text',
        })
        textIndex += 1
        builders.push((row) => {
          const raw = row[col] ?? ''
          const days = raw.match(/^(\d+)\s+days?/)
          return [cell(raw, days ? Number(days[1]) : raw.toLowerCase())]
        })
      }
    }
  })

  const rows = items.map((row) => builders.flatMap((build) => build(row)))

  // Column totals are only honest when every row is on screen.
  let totals = null
  if (!more && rows.length > 1) {
    const sums = columns.map((column, index) => {
      if (column.kind !== 'money') return null
      return rows.reduce((sum, row) => sum + (typeof row[index].sort === 'number' ? row[index].sort : 0), 0)
    })
    if (sums.some((sum) => sum !== null)) {
      totals = sums.map((sum) => (sum === null ? null : formatRupees(sum)))
    }
  }

  // Give duplicate labels a suffix so headers stay distinguishable.
  const seen = {}
  columns.forEach((column) => {
    seen[column.label] = (seen[column.label] || 0) + 1
    if (seen[column.label] > 1) column.label = `${column.label} ${seen[column.label]}`
  })

  return { type: 'table', columns, rows, totals, more }
}

function flushBullets(bullets, blocks, heading) {
  if (bullets.length === 0) return
  const parsed = bullets.map(bulletCells)
  const width = parsed[0]?.length
  const tabular =
    parsed.every((cells) => cells && cells.length === width) && width >= 2

  if (tabular) {
    blocks.push(buildTable(parsed, heading, null))
  } else {
    blocks.push({ type: 'list', items: bullets.slice() })
  }
  bullets.length = 0
}

export function parseChatAnswer(text) {
  const result = { blocks: [], fromTally: false }
  if (typeof text !== 'string' || !text.trim()) return result

  const blocks = result.blocks
  const bullets = []
  let stats = []
  let meta = []
  let heading = null

  const flushStats = () => {
    if (stats.length) blocks.push({ type: 'stats', items: stats })
    if (meta.length) blocks.push({ type: 'meta', items: meta })
    stats = []
    meta = []
  }

  const flushAll = () => {
    flushBullets(bullets, blocks, heading)
    flushStats()
  }

  for (const rawLine of text.replace(/\r\n?/g, '\n').split('\n')) {
    let line = rawLine.trim()

    if (!line) {
      flushAll()
      continue
    }

    if (FROM_TALLY.test(line)) {
      result.fromTally = true
      line = line.replace(FROM_TALLY, ' ').replace(/\s+:/, ':').replace(/\s{2,}/g, ' ').trim()
    }

    const more = line.match(MORE)
    if (more) {
      flushBullets(bullets, blocks, heading)
      const last = blocks[blocks.length - 1]
      const count = Number(more[1].replace(/,/g, ''))
      if (last && (last.type === 'table' || last.type === 'list')) {
        last.more = count
        // Totals over a partial list would understate the real figure.
        if (last.type === 'table') last.totals = null
      } else {
        blocks.push({ type: 'paragraph', text: line })
      }
      continue
    }

    const bullet = line.match(BULLET)
    if (bullet) {
      flushStats()
      bullets.push(bullet[1].trim())
      continue
    }

    flushBullets(bullets, blocks, heading)

    if (isHeading(line)) {
      flushStats()
      heading = line.slice(0, -1).trim()
      blocks.push({ type: 'heading', text: heading })
      continue
    }

    const kv = splitKeyValue(line)
    if (kv) {
      // "Ledgers: 11" introduces the list below it just like a heading.
      heading = kv.label
      const drcr = kv.value.match(DR_CR)
      if (STAT_VALUE.test(kv.value) && kv.value.length <= 32) {
        stats.push(
          drcr
            ? { label: kv.label, value: drcr[1].replace(/\s+/g, ''), side: drcr[2][0].toUpperCase() + drcr[2].slice(1).toLowerCase() }
            : { label: kv.label, value: kv.value },
        )
      } else {
        meta.push(kv)
      }
      continue
    }

    flushStats()
    blocks.push({ type: 'paragraph', text: line })
  }

  flushAll()
  return result
}

/* Plain-text version of a table, for copying into a spreadsheet or mail. */
export function tableToTsv(table) {
  const lines = [table.columns.map((column) => column.label).join('\t')]
  table.rows.forEach((row) => lines.push(row.map((value) => value.display).join('\t')))
  if (table.totals) {
    lines.push(table.totals.map((value, index) => (index === 0 ? 'Total' : value ?? '')).join('\t'))
  }
  return lines.join('\n')
}
