import test from 'node:test'
import assert from 'node:assert/strict'

import { parseChatAnswer, tableToTsv } from '../src/utils/chatAnswerParser.js'

const BANK_ANSWER = [
  'HDFC Bank Transactions (from Tally):',
  'Opening Balance: ₹0',
  'Closing Balance: ₹32,85,000',
  'Total Transactions: 3',
  '',
  '• 2025-04-01 | Receipt #4 | Bajaj Finance | ₹20,00,000 Dr',
  '• 2025-04-02 | Payment #1 | Apex Office Solutions | ₹10,00,000 Cr',
  '• 2026-02-01 | Contra #1 | Cash | ₹10,000 Cr',
].join('\n')

test('bank voucher list becomes heading, stat tiles and a Tally-style table', () => {
  const { blocks, fromTally } = parseChatAnswer(BANK_ANSWER)

  assert.equal(fromTally, true)
  assert.deepEqual(blocks.map((block) => block.type), ['heading', 'stats', 'table'])
  assert.equal(blocks[0].text, 'HDFC Bank Transactions')
  assert.deepEqual(blocks[1].items.map((item) => item.label), [
    'Opening Balance', 'Closing Balance', 'Total Transactions',
  ])

  const table = blocks[2]
  assert.deepEqual(table.columns.map((column) => column.label), [
    'Date', 'Vch Type', 'Vch No.', 'Particulars', 'Debit', 'Credit',
  ])
  assert.deepEqual(table.rows[0].map((cell) => cell.display), [
    '1-Apr-2025', 'Receipt', '4', 'Bajaj Finance', '₹20,00,000', '',
  ])
  assert.deepEqual(table.rows[1].map((cell) => cell.display).slice(4), ['', '₹10,00,000'])
  assert.equal(table.rows[0][0].sort, '2025-04-01')
  assert.deepEqual(table.totals.slice(4), ['₹20,00,000', '₹10,10,000'])
})

test('a truncated list keeps the hidden-row count and drops totals', () => {
  const { blocks } = parseChatAnswer(
    `${BANK_ANSWER}\n... and 12 more transactions.`,
  )
  const table = blocks.find((block) => block.type === 'table')
  assert.equal(table.more, 12)
  assert.equal(table.totals, null)
})

test('ledger list gets Ledger / Group headers', () => {
  const { blocks } = parseChatAnswer([
    'Ledgers (from Tally): 2',
    '- Sweeper Salary | Indirect Expenses',
    '- Sweeper Salary Payable | Provisions',
  ].join('\n'))

  assert.equal(blocks[0].type, 'stats')
  assert.equal(blocks[0].items[0].label, 'Ledgers')
  assert.deepEqual(blocks[1].columns.map((column) => column.label), ['Ledger', 'Group'])
})

test('name: amount bullets become a two column table', () => {
  const { blocks } = parseChatAnswer([
    'TDS Ledgers:',
    '- TDS on Rent: ₹12,000',
    '- TDS on Contract: ₹8,500.50',
  ].join('\n'))

  const table = blocks[1]
  assert.deepEqual(table.columns.map((column) => column.label), ['Name', 'Amount'])
  assert.equal(table.columns[1].align, 'right')
  assert.equal(table.totals[1], '₹20,500.50')
})

test('trial-balance style labelled amounts become their own columns', () => {
  const { blocks } = parseChatAnswer([
    '• Cash: Debit ₹10,000 | Credit ₹0',
    '• Capital: Debit ₹0 | Credit ₹5,00,000',
  ].join('\n'))

  assert.deepEqual(blocks[0].columns.map((column) => column.label), ['Name', 'Debit', 'Credit'])
  assert.equal(blocks[0].rows[1][2].display, '₹5,00,000')
})

test('overdue invoices label the days column', () => {
  const { blocks } = parseChatAnswer([
    'You have 2 overdue invoice(s) in Tally.',
    '- Eagle Paradise | INV-1 | ₹50,000 | 40 days overdue',
    '- Apex | INV-2 | ₹5,000 | 12 days overdue',
  ].join('\n'))

  assert.equal(blocks[0].type, 'paragraph')
  assert.deepEqual(blocks[1].columns.map((column) => column.label), [
    'Name', 'Details', 'Amount', 'Overdue',
  ])
  assert.equal(blocks[1].rows[0][3].sort, 40)
})

test('plain prose stays as paragraphs', () => {
  const text = 'HDFC Bank has an opening balance of ₹0 and no transactions in the selected period.'
  const { blocks } = parseChatAnswer(text)
  assert.deepEqual(blocks, [{ type: 'paragraph', text }])
})

test('mixed bullets fall back to a list', () => {
  const { blocks } = parseChatAnswer('- Check GST filing\n- Name | Value | Extra')
  assert.equal(blocks[0].type, 'list')
  assert.equal(blocks[0].items.length, 2)
})

test('non-numeric key/values become meta, not stat tiles', () => {
  const { blocks } = parseChatAnswer('Period: 2025-04-01 to 2026-03-31\nRevenue: ₹1,20,000')
  assert.deepEqual(blocks.map((block) => block.type), ['stats', 'meta'])
})

test('tableToTsv exports headers, rows and totals', () => {
  const table = parseChatAnswer(BANK_ANSWER).blocks[2]
  const tsv = tableToTsv(table).split('\n')
  assert.equal(tsv[0], 'Date\tVch Type\tVch No.\tParticulars\tDebit\tCredit')
  assert.equal(tsv.at(-1), 'Total\t\t\t\t₹20,00,000\t₹10,10,000')
})

test('empty or non-string answers produce no blocks', () => {
  assert.deepEqual(parseChatAnswer('').blocks, [])
  assert.deepEqual(parseChatAnswer(undefined).blocks, [])
})
