import { Link } from 'react-router'
import { ChevronRight } from 'lucide-react'

import PageHeader from '../components/layout/PageHeader'
import { REPORT_ICONS } from '../components/layout/navConfig'
import { ALL_REPORTS } from '../reportsConfig'

function ReportsIndex() {
  return (
    <div className="reports-index">
      <PageHeader
        title="Reports"
        subtitle="Every report in one place — pick one to view, or export it as PDF / Excel."
      />

      <div className="reports-grid">
        {ALL_REPORTS.map((report) => {
          const Icon = REPORT_ICONS[report.to]

          return (
            <Link key={report.to} to={report.to} className="report-card">
              {Icon && (
                <span className="report-card-icon">
                  <Icon size={18} />
                </span>
              )}
              <span className="report-card-body">
                <span className="report-card-title">{report.label}</span>
                <span className="report-card-desc">{report.description}</span>
              </span>
              <ChevronRight size={16} className="report-card-arrow" />
            </Link>
          )
        })}
      </div>
    </div>
  )
}

export default ReportsIndex
