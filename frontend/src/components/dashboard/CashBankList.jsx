import { formatBalance } from './format'

// Every ledger under Cash-in-Hand or Bank Accounts, largest balance first.
function CashBankList({ accounts }) {
  const sorted = [...accounts].sort(
    (a, b) => Math.abs(Number(b.balance) || 0) - Math.abs(Number(a.balance) || 0)
  )

  return (
    <div className="db-table-scroll">
      <table className="db-table">
        <thead>
          <tr>
            <th scope="col">Account</th>
            <th scope="col" className="db-hide-sm">Type</th>
            <th scope="col" className="db-num">Closing balance</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((account) => (
            <tr key={account.name}>
              <td><span className="db-party" title={account.name}>{account.name}</span></td>
              <td className="db-hide-sm"><span className="db-chip">{account.category}</span></td>
              <td className="db-num">{formatBalance(account.balance)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default CashBankList
