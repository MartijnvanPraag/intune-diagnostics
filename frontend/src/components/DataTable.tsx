import React, { useState, useMemo } from 'react'
import { TableData } from '@/services/diagnosticsService'

interface DataTableProps {
  data: TableData
  title?: string
}

const DataTable: React.FC<DataTableProps> = ({ data, title }) => {
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(25)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)

  const total = data?.rows?.length || 0
  const pageCount = Math.ceil(total / pageSize) || 1
  const pagedRows = useMemo(() => {
    const start = page * pageSize
    return data.rows.slice(start, start + pageSize)
  }, [data.rows, page, pageSize])

  const goPage = (p: number) => {
    if (p < 0 || p >= pageCount) return
    setExpandedRow(null)
    setPage(p)
  }

  const downloadCSV = () => {
    const esc = (v: any) => '"' + String(v).replace(/"/g,'""') + '"'
    const csv = [data.columns.map(esc).join(',')]
    data.rows.forEach(r => csv.push(r.map(esc).join(',')))
    const blob = new Blob([csv.join('\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = (title || 'table') + '.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const downloadJSON = () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = (title || 'table') + '.json'
    a.click()
    URL.revokeObjectURL(url)
  }
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
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-medium text-win11-text-primary">{title || 'Query Results'}</h3>
        <div className="flex items-center gap-2 text-xs">
          <button onClick={downloadCSV} className="px-2 py-1 border border-win11-border rounded hover:bg-win11-surfaceHover">CSV</button>
          <button onClick={downloadJSON} className="px-2 py-1 border border-win11-border rounded hover:bg-win11-surfaceHover">JSON</button>
          <select value={pageSize} onChange={e=>{setPageSize(parseInt(e.target.value)); setPage(0)}} className="px-1 py-1 border border-win11-border rounded bg-win11-surface">
            {[10,25,50,100].map(s=> <option key={s} value={s}>{s}/page</option>)}
          </select>
        </div>
      </div>
      
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
              <th className="px-2 py-3 text-left text-xs font-medium text-win11-text-secondary uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-win11-border">
            {pagedRows.map((row, rowIndex) => {
              const globalIndex = page*pageSize + rowIndex
              const expanded = expandedRow === globalIndex
              return (
              <tr
                key={globalIndex}
                className="hover:bg-win11-surfaceHover transition-colors align-top"
              >
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="px-4 py-3 text-sm text-win11-text-primary">
                    {expanded && typeof cell === 'string' && cell.length > 120 ? (
                      <pre className="whitespace-pre-wrap text-[11px] max-h-80 overflow-auto bg-win11-surface p-2 rounded border border-win11-border">{cell}</pre>
                    ) : (
                      (cell !== null && cell !== undefined ? String(cell).slice(0,120) + (String(cell).length>120?'…':'') : '-')
                    )}
                  </td>
                ))}
                <td className="px-2 py-3 text-xs">
                  <button onClick={()=> setExpandedRow(expanded ? null : globalIndex)} className="px-2 py-1 border border-win11-border rounded hover:bg-win11-surfaceHover">
                    {expanded ? 'Collapse' : 'Expand'}
                  </button>
                </td>
              </tr>
            )})}
          </tbody>
        </table>
      </div>
      
      <div className="mt-4 flex items-center justify-between text-xs text-win11-text-tertiary">
        <div>
          Rows {page*pageSize + 1}-{Math.min((page+1)*pageSize, total)} of {total}{data.total_rows>total?` (source total ${data.total_rows})`:''}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={()=>goPage(0)} disabled={page===0} className="px-2 py-1 border border-win11-border rounded disabled:opacity-40">⟪</button>
          <button onClick={()=>goPage(page-1)} disabled={page===0} className="px-2 py-1 border border-win11-border rounded disabled:opacity-40">◀</button>
          <span>Page {page+1}/{pageCount}</span>
          <button onClick={()=>goPage(page+1)} disabled={page>=pageCount-1} className="px-2 py-1 border border-win11-border rounded disabled:opacity-40">▶</button>
          <button onClick={()=>goPage(pageCount-1)} disabled={page>=pageCount-1} className="px-2 py-1 border border-win11-border rounded disabled:opacity-40">⟫</button>
        </div>
      </div>
    </div>
  )
}

export default DataTable