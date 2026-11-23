import { Landmark, Wallet } from 'lucide-react'
import { formatAmount, formatBalance } from './format'

// Every ledger under Cash-in-Hand or Bank Accounts, largest balance first.
function CashBankList({ accounts }) {
  const sorted = [...accounts].sort(
    (a, b) => Math.abs(Number(b.balance) || 0) - Math.abs(Number(a.balance) || 0)
  )

  // Calculate total liquid funds
  const totalLiquidity = sorted.reduce((sum, item) => sum + (Number(item.balance) || 0), 0)
  const maxAbsBalance = sorted.reduce(
    (max, item) => Math.max(max, Math.abs(Number(item.balance) || 0)),
    0
  ) || 1

  const bankCount = sorted.filter((a) => (a.category || '').toLowerCase().includes('bank')).length
  const cashCount = sorted.length - bankCount

  return (
    <div className="db-cash-bank-container">
      <div className="db-treasury-summary">
        <div className="db-treasury-metric">
          <span className="db-treasury-label">Total Liquid Treasury</span>
          <span className="db-treasury-val">{formatBalance(totalLiquidity)}</span>
        </div>
        <div className="db-treasury-split">
          <span className="db-treasury-chip db-treasury-chip--bank">
            <Landmark size={12} aria-hidden="true" />
            {bankCount} {bankCount === 1 ? 'Bank' : 'Banks'}
          </span>
          <span className="db-treasury-chip db-treasury-chip--cash">
            <Wallet size={12} aria-hidden="true" />
            {cashCount} {cashCount === 1 ? 'Cash' : 'Cash'}
          </span>
        </div>
      </div>

      <div className="db-table-scroll">
        <table className="db-table">
          <thead>
            <tr>
              <th scope="col">Ledger Account</th>
              <th scope="col" className="db-hide-sm">Category</th>
              <th scope="col" className="db-num">Closing Balance</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((account) => {
              const isBank = (account.category || '').toLowerCase().includes('bank')
              const rawBal = Number(account.balance) || 0
              const absVal = Math.abs(rawBal)
              const share = ((absVal / maxAbsBalance) * 100).toFixed(0)
              const isDebit = rawBal <= 0 // Tally: negative is Dr (Asset), positive is Cr (Overdraft/Liability)

              return (
                <tr key={account.name} className="db-ledger-row">
                  <td>
                    <div className="db-ledger-identity">
                      <span className={`db-ledger-avatar ${isBank ? 'is-bank' : 'is-cash'}`} aria-hidden="true">
                        {isBank ? <Landmark size={14} /> : <Wallet size={14} />}
                      </span>
                      <div className="db-ledger-info">
                        <span className="db-party" title={account.name}>{account.name}</span>
                        <div className="db-ledger-share-bar">
                          <span
                            className={`db-ledger-share-fill ${isDebit ? 'is-dr' : 'is-cr'}`}
                            style={{ width: `${share}%` }}
                            aria-hidden="true"
                          />
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="db-hide-sm">
                    <span className={`db-chip ${isBank ? 'db-chip--bank' : 'db-chip--cash'}`}>
                      {account.category || (isBank ? 'Bank Account' : 'Cash-in-Hand')}
                    </span>
                  </td>
                  <td className="db-num">
                    <div className="db-balance-cell">
                      <span className="db-balance-num">{formatAmount(absVal)}</span>
                      <span className={`db-drcr-pill ${isDebit ? 'db-drcr--dr' : 'db-drcr--cr'}`}>
                        {isDebit ? 'Dr (Asset)' : 'Cr (Overdraft)'}
                      </span>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default CashBankList
