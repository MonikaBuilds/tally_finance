import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, Check, Copy, Search } from 'lucide-react'
import { tableToTsv } from '../../utils/chatAnswerParser'
import useCopy from './useCopy'

// Long answers are scanned, not read: show a screenful, let people opt in to more.
const PREVIEW_ROWS = 8

function compare(a, b) {
  if (a === b) return 0
  if (a === null || a === '') return 1
  if (b === null || b === '') return -1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b), 'en-IN', { numeric: true })
}


function AnswerTable({ table, caption }) {
  const [sort, setSort] = useState(null)
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [copied, copy] = useCopy()

  const { columns, totals, more } = table
  const searchable = table.rows.length > PREVIEW_ROWS

  const rows = useMemo(() => {
    let result = table.rows
    const needle = query.trim().toLowerCase()
    if (needle) {
      result = result.filter((row) =>
        row.some((cell) => cell.display.toLowerCase().includes(needle)),
      )
    }
    if (sort) {
      result = [...result].sort((left, right) => {
        const order = compare(left[sort.index].sort, right[sort.index].sort)
        return sort.dir === 'asc' ? order : -order
      })
    }
    return result
  }, [table.rows, query, sort])

  const filtering = query.trim() !== ''
  const visible = expanded || filtering ? rows : rows.slice(0, PREVIEW_ROWS)
  const hiddenCount = rows.length - visible.length

  function toggleSort(index) {
    setSort((current) => {
      if (!current || current.index !== index) {
        // Amounts are most useful largest-first; text and dates A→Z / oldest first.
        return { index, dir: columns[index].align === 'right' ? 'desc' : 'asc' }
      }
      if (current.dir === (columns[index].align === 'right' ? 'desc' : 'asc')) {
        return { index, dir: current.dir === 'asc' ? 'desc' : 'asc' }
      }
      return null
    })
  }

  const totalLabelIndex = totals ? totals.findIndex((value) => value === null) : -1

  return (
    <div className="answer-table">
      <div className="answer-table__toolbar">
        <span className="answer-table__count">
          {filtering
            ? `${rows.length} of ${table.rows.length} entries`
            : `${table.rows.length}${more ? ` of ${table.rows.length + more}` : ''} entries`}
        </span>

        <div className="answer-table__tools">
          {searchable && (
            <label className="answer-table__search">
              <Search size={14} aria-hidden="true" />
              <input
                type="search"
                placeholder="Filter rows"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label={`Filter ${caption || 'table'} rows`}
              />
            </label>
          )}
          <button
            type="button"
            className="chat-icon-btn"
            onClick={() => copy(tableToTsv(table))}
            title="Copy table (pastes into Excel)"
            aria-label="Copy table"
          >
            {copied ? <Check size={15} /> : <Copy size={15} />}
          </button>
        </div>
      </div>

      <div className="answer-table__scroll">
        <table>
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead>
            <tr>
              {columns.map((column, index) => {
                const active = sort?.index === index
                const SortIcon = !active ? ArrowUpDown : sort.dir === 'asc' ? ArrowUp : ArrowDown
                return (
                  <th
                    key={column.label}
                    scope="col"
                    className={column.align === 'right' ? 'num' : undefined}
                    aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  >
                    <button type="button" onClick={() => toggleSort(index)}>
                      {column.label}
                      <SortIcon size={12} aria-hidden="true" className={active ? 'is-active' : ''} />
                    </button>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, index) => (
                  <td
                    key={columns[index].label}
                    className={columns[index].align === 'right' ? 'num' : undefined}
                  >
                    {cell.display}
                  </td>
                ))}
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="answer-table__empty">
                  No rows match “{query}”.
                </td>
              </tr>
            )}
          </tbody>
          {totals && !filtering && (
            <tfoot>
              <tr>
                {totals.map((value, index) => (
                  <td
                    key={columns[index].label}
                    className={columns[index].align === 'right' ? 'num' : undefined}
                  >
                    {index === totalLabelIndex
                      ? hiddenCount > 0 ? `Total (all ${rows.length})` : 'Total'
                      : value ?? ''}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {(hiddenCount > 0 || (expanded && rows.length > PREVIEW_ROWS && !filtering)) && (
        <button
          type="button"
          className="answer-table__expand"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? 'Show fewer' : `Show all ${rows.length} entries`}
        </button>
      )}

      {more > 0 && (
        <p className="answer-table__more">
          {more} more {more === 1 ? 'entry is' : 'entries are'} not shown in chat.
          Download the Excel file for the complete list.
        </p>
      )}
    </div>
  )
}

export default AnswerTable
