import React from 'react'
import { TableData } from '@/services/diagnosticsService'

interface DataTableProps {
  data: TableData
  title?: string
}

const DataTable: React.FC<DataTableProps> = ({ data, title }) => {
  if (!data || !data.rows || data.rows.length === 0) {
    return (
      <div className="win11-card p-6">
        <h3 className="text-lg font-medium text-win11-text-primary mb-4">
          {title || 'Query Results'}
        </h3>
        <div className="text-center py-8">
          <div className="text-win11-text-tertiary">No data available</div>
        </div>
      </div>
    )
  }

  return (
    <div className="win11-card p-6">
      {title && (
        <h3 className="text-lg font-medium text-win11-text-primary mb-4">
          {title}
        </h3>
      )}
      
      <div className="overflow-x-auto">
        <table className="min-w-full">
          <thead>
            <tr className="border-b border-win11-border">
              {data.columns.map((column, index) => (
                <th
                  key={index}
                  className="px-4 py-3 text-left text-xs font-medium text-win11-text-secondary uppercase tracking-wider"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-win11-border">
            {data.rows.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                className="hover:bg-win11-surfaceHover transition-colors"
              >
                {row.map((cell, cellIndex) => (
                  <td
                    key={cellIndex}
                    className="px-4 py-3 text-sm text-win11-text-primary"
                  >
                    {cell !== null && cell !== undefined ? String(cell) : '-'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      {data.total_rows > data.rows.length && (
        <div className="mt-4 text-sm text-win11-text-tertiary text-center">
          Showing {data.rows.length} of {data.total_rows} rows
        </div>
      )}
    </div>
  )
}

export default DataTable