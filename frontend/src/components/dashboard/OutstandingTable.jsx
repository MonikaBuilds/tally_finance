import { AlertTriangle, Clock, Calendar, FileText } from 'lucide-react'

import { formatAmount, formatDay } from './format'

// Tally leaves the Overdue column blank until a bill is past due, so a
// blank with a due date means "not yet due", not "unknown".
function OverdueStatus({ days, dueDate }) {
  if ((days === null || days === undefined) && !dueDate) {
    return (
      <span className="db-chip db-chip--ondemand">
        <Clock size={11} aria-hidden="true" />
        On demand
      </span>
    )
  }

  if (days > 0) {
    const isCritical = days > 60
    return (
      <span className={`db-chip ${isCritical ? 'db-chip--critical' : 'db-chip--overdue'}`}>
        <AlertTriangle size={11} aria-hidden="true" />
        {days} {days === 1 ? 'day' : 'days'} overdue
      </span>
    )
  }

  return (
    <span className="db-chip db-chip--due">
      <Clock size={11} aria-hidden="true" />
      Within terms
    </span>
  )
}

// Largest pending bills from Tally's Bills Receivable / Payable report.
function OutstandingTable({ bills, partyLabel }) {
  return (
    <div className="db-table-scroll">
      <table className="db-table db-table--outstanding">
        <thead>
          <tr>
            <th scope="col">{partyLabel} / Voucher</th>
            <th scope="col" className="db-hide-sm">Due Date</th>
            <th scope="col">Credit Status</th>
            <th scope="col" className="db-num">Pending Amount</th>
          </tr>
        </thead>
        <tbody>
          {bills.map((bill, index) => (
            <tr key={`${bill.party}-${bill.reference}-${index}`} className="db-bill-row">
              <td>
                <div className="db-bill-party-cell">
                  <span className="db-party" title={bill.party}>
                    {bill.party}
                  </span>
                  {bill.reference && (
                    <span className="db-ref">
                      <FileText size={10} aria-hidden="true" />
                      {bill.reference}
                    </span>
                  )}
                </div>
              </td>
              <td className="db-nowrap db-hide-sm">
                <span className="db-date-cell">
                  <Calendar size={11} aria-hidden="true" />
                  {bill.due_date ? formatDay(bill.due_date) : '—'}
                </span>
              </td>
              <td>
                <OverdueStatus days={bill.days_overdue} dueDate={bill.due_date} />
              </td>
              <td className="db-num">
                <span className="db-amount-highlight">{formatAmount(bill.amount)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default OutstandingTable
