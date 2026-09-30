import { AlertTriangle, Clock } from 'lucide-react'

import { formatAmount, formatDay } from './format'

// Tally leaves the Overdue column blank until a bill is past due, so a
// blank with a due date means "not yet due", not "unknown".
function OverdueStatus({ days, dueDate }) {
  if ((days === null || days === undefined) && !dueDate) {
    return <span className="db-chip">No due date</span>
  }

  if (days > 0) {
    return (
      <span className="db-chip db-chip--overdue">
        <AlertTriangle size={12} aria-hidden="true" />
        {days} {days === 1 ? 'day' : 'days'} overdue
      </span>
    )
  }

  return (
    <span className="db-chip db-chip--due">
      <Clock size={12} aria-hidden="true" />
      Not yet due
    </span>
  )
}

// Largest pending bills from Tally's Bills Receivable / Payable report.
function OutstandingTable({ bills, partyLabel }) {
  return (
    <div className="db-table-scroll">
      <table className="db-table">
        <thead>
          <tr>
            <th scope="col">{partyLabel}</th>
            <th scope="col" className="db-hide-sm">Due on</th>
            <th scope="col">Status</th>
            <th scope="col" className="db-num">Pending</th>
          </tr>
        </thead>
        <tbody>
          {bills.map((bill, index) => (
            <tr key={`${bill.party}-${bill.reference}-${index}`}>
              <td>
                <span className="db-party" title={bill.party}>{bill.party}</span>
                {bill.reference && <span className="db-ref">Ref {bill.reference}</span>}
              </td>
              <td className="db-nowrap db-hide-sm">{bill.due_date ? formatDay(bill.due_date) : '—'}</td>
              <td><OverdueStatus days={bill.days_overdue} dueDate={bill.due_date} /></td>
              <td className="db-num">{formatAmount(bill.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default OutstandingTable
