import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import { TableData } from '@/services/diagnosticsService'

interface DataTableProps {
  data: TableData
  title?: string
}

const DataTable: React.FC<DataTableProps> = ({ data, title }) => {
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(25)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  const [renderedMermaid, setRenderedMermaid] = useState(false)
  const [mermaidError, setMermaidError] = useState<string | null>(null)
  const [showMermaidDebug, setShowMermaidDebug] = useState(false)
  const [normalizedMermaid, setNormalizedMermaid] = useState<string | null>(null)
  const [showMermaidModal, setShowMermaidModal] = useState(false)
  const [modalPosition, setModalPosition] = useState({ x: 100, y: 100 })
  const [modalSize, setModalSize] = useState({ width: 1000, height: 700 })
  const [isDragging, setIsDragging] = useState(false)
  const [isResizing, setIsResizing] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })
  const [resizeStart, setResizeStart] = useState({ x: 0, y: 0, width: 0, height: 0 })
  const mermaidContainerRef = useRef<HTMLDivElement | null>(null)

  // Detect if this table contains a mermaid timeline column signature
  const isMermaidTimeline = useMemo(() => {
    if (!data || !data.columns || data.columns.length !== 1) return false
    const col = data.columns[0].toLowerCase()
    if (col === 'mermaid_timeline') return true
    return false
  }, [data])

  const diagramSource = useMemo(() => {
    if (!isMermaidTimeline) return null
    if (data.rows && data.rows.length > 0) {
      const raw = data.rows[0][0]
      if (typeof raw === 'string') return raw.trim()
    }
    return null
  }, [isMermaidTimeline, data])

  const handleRenderMermaid = useCallback(() => {
    if (!diagramSource) return
    setMermaidError(null)
    setShowMermaidModal(true)
    setRenderedMermaid(true) // actual rendering occurs in effect after container mounts
  }, [diagramSource])

  // Drag functionality
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    setIsDragging(true)
    setDragStart({ x: e.clientX - modalPosition.x, y: e.clientY - modalPosition.y })
  }, [modalPosition])

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (isDragging) {
      setModalPosition({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y
      })
    } else if (isResizing) {
      const newWidth = Math.max(400, e.clientX - resizeStart.x + resizeStart.width)
      const newHeight = Math.max(300, e.clientY - resizeStart.y + resizeStart.height)
      setModalSize({ width: newWidth, height: newHeight })
    }
  }, [isDragging, isResizing, dragStart, resizeStart])

  const handleMouseUp = useCallback(() => {
    setIsDragging(false)
    setIsResizing(false)
  }, [])

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    setIsResizing(true)
    setResizeStart({
      x: e.clientX,
      y: e.clientY,
      width: modalSize.width,
      height: modalSize.height
    })
  }, [modalSize])

  // Global mouse events for drag/resize
  useEffect(() => {
    if (isDragging || isResizing) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      return () => {
        document.removeEventListener('mousemove', handleMouseMove)
        document.removeEventListener('mouseup', handleMouseUp)
      }
    }
  }, [isDragging, isResizing, handleMouseMove, handleMouseUp])

  useEffect(() => {
    const render = async () => {
      if (!renderedMermaid || !diagramSource || !showMermaidModal) return
      try {
        const mermaid = (await import('mermaid')).default
        if (!(mermaid as any)._intuneDiagnosticsInitialized) {
          await mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'strict' })
          ;(mermaid as any)._intuneDiagnosticsInitialized = true
        }
        // Normalize model-produced timeline text to Mermaid's expected 'timeline' grammar.
        // Build and attempt multiple normalization strategies until one parses
        const baseFallback = 'gantt\ntitle Device Timeline\ndateFormat YYYY-MM-DD\naxisFormat %m-%d\nsection Events\nNo data :1970-01-01, 1970-01-01'
        
        const normalize = (raw: string) => {
          if (!raw) return baseFallback
          
          // Extract fenced block if present
          const fenced = raw.match(/```mermaid[\s\S]*?```/i)
          if (fenced) {
            raw = fenced[0].replace(/```mermaid/i,'').replace(/```$/,'')
          }
          
          // Split into lines and clean up
          let lines = raw.replace(/\r/g,'').split('\n')
            .map(l => l.replace(/\t/g, '    ')) // convert tabs to spaces
            .map(l => l.trimEnd()) // remove trailing whitespace
          
          // Remove empty lines at start
          while(lines.length && lines[0].trim() === '') lines.shift()
          
          // Stop at blank line or delimiter
          const firstBlank = lines.findIndex(l => l.trim() === '' || l.trim() === '---')
          if (firstBlank > 0) lines = lines.slice(0, firstBlank)
          
          if (!lines.length) return baseFallback
          
          // Extract title and events
          let titleContent = 'Device Timeline'
          const events: Array<{date: string, time: string, description: string}> = []
          
          for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed) continue
            
            // Skip timeline directive and start line
            if (/^timeline\b/i.test(trimmed) || /^start\s*:/i.test(trimmed)) {
              continue
            }
            
            // Extract title
            if (/^\s*title\s*:/i.test(trimmed)) {
              titleContent = trimmed.replace(/^\s*title\s*:\s*/i, '').trim()
              continue
            }
            
            // Parse event lines with timestamps
            const eventMatch = trimmed.match(/^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})\s*:\s*(.+)$/)
            if (eventMatch) {
              const [, date, time, description] = eventMatch
              events.push({ date, time, description })
            }
          }
          
          if (!events.length) {
            return baseFallback
          }
          
          // Gantt charts work better for showing events over time
          const result = ['gantt', `title ${titleContent}`, 'dateFormat YYYY-MM-DD', 'axisFormat %m-%d']
          
          // Group events by type for better visualization
          const eventTypes = new Map<string, Array<{date: string, time: string, description: string}>>()
          
          events.forEach(event => {
            // Extract event type from description (first word before dash)
            const typeMatch = event.description.match(/^([^-]+)/)
            const type = typeMatch ? typeMatch[1].trim() : 'Event'
            
            if (!eventTypes.has(type)) {
              eventTypes.set(type, [])
            }
            eventTypes.get(type)!.push(event)
          })
          
          // Add sections and tasks for each event type
          for (const [type, typeEvents] of eventTypes) {
            result.push(`section ${type}`)
            
            typeEvents.forEach((event) => {
              // Create meaningful task names while being very careful about special characters
              const fullDesc = event.description.substring(event.description.indexOf('-') + 1).trim()
              
              // Clean the description to avoid parser issues
              const cleanDesc = fullDesc
                .replace(/[()]/g, '') // Remove parentheses
                .replace(/["']/g, '') // Remove quotes
                .replace(/[^\w\s\-.,]/g, '') // Remove other special chars, keep basic punctuation
                .replace(/\s+/g, ' ') // Normalize spaces
                .trim()
                // Don't limit length - let's see how much Mermaid can handle
              
              const taskName = `${event.time.replace(':', 'h')} ${cleanDesc}`
              
              result.push(`${taskName} :${event.date}, ${event.date}`)
            })
          }
          
          return result.join('\n')
        }
        
        const source = normalize(diagramSource)
        setNormalizedMermaid(source)
        // Use stable id based on hash of content for potential re-renders
        const id = 'mermaid_timeline_' + btoa(unescape(encodeURIComponent(source))).slice(0,12)
        const { svg } = await mermaid.render(id, source)
        if (mermaidContainerRef.current) {
          mermaidContainerRef.current.innerHTML = svg
        }
      } catch (e: any) {
        console.error('Mermaid render failed', e)
        setMermaidError(e?.message || String(e))
      }
    }
    render()
  }, [renderedMermaid, diagramSource, showMermaidModal])

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
          {isMermaidTimeline && diagramSource && (
            <button onClick={handleRenderMermaid} className="px-2 py-1 border border-blue-500 text-blue-600 rounded hover:bg-blue-50" title="Open timeline in modal">
              Open Timeline
            </button>
          )}
          <button onClick={downloadCSV} className="px-2 py-1 border border-win11-border rounded hover:bg-win11-surfaceHover">CSV</button>
          <button onClick={downloadJSON} className="px-2 py-1 border border-win11-border rounded hover:bg-win11-surfaceHover">JSON</button>
          <select value={pageSize} onChange={e=>{setPageSize(parseInt(e.target.value)); setPage(0)}} className="px-1 py-1 border border-win11-border rounded bg-win11-surface">
            {[10,25,50,100].map(s=> <option key={s} value={s}>{s}/page</option>)}
          </select>
        </div>
      </div>

      {/* Mermaid Modal */}
      {showMermaidModal && (
        <div className="fixed inset-0 bg-black bg-opacity-30 z-50">
          <div 
            className="absolute bg-white rounded-lg shadow-2xl flex flex-col border border-gray-300"
            style={{
              left: modalPosition.x,
              top: modalPosition.y,
              width: modalSize.width,
              height: modalSize.height,
              minWidth: '400px',
              minHeight: '300px'
            }}
          >
            {/* Modal Header - Draggable */}
            <div 
              className="flex items-center justify-between p-4 border-b border-win11-border cursor-move bg-gray-50 rounded-t-lg"
              onMouseDown={handleMouseDown}
            >
              <h3 className="text-lg font-medium text-win11-text-primary select-none">Device Timeline</h3>
              <div className="flex items-center gap-2">
                <button 
                  onClick={() => setShowMermaidDebug(v => !v)} 
                  className="px-2 py-1 text-xs border border-purple-500 text-purple-600 rounded hover:bg-purple-50"
                  title="Toggle source view"
                  onMouseDown={(e) => e.stopPropagation()}
                >
                  {showMermaidDebug ? 'Hide Source' : 'Show Source'}
                </button>
                <button 
                  onClick={() => setShowMermaidModal(false)}
                  className="text-win11-text-secondary hover:text-win11-text-primary text-xl font-bold w-8 h-8 flex items-center justify-center rounded hover:bg-win11-surfaceHover"
                  title="Close modal"
                  onMouseDown={(e) => e.stopPropagation()}
                >
                  ×
                </button>
              </div>
            </div>
            
            {/* Modal Content */}
            <div className="flex-1 p-4 overflow-auto">
              {mermaidError ? (
                <div className="text-red-600 text-sm">Render error: {mermaidError}</div>
              ) : (
                <div className="space-y-4">
                  <div ref={mermaidContainerRef} className="min-w-full overflow-x-auto" />
                  {showMermaidDebug && (
                    <div className="border-t border-win11-border pt-4">
                      <div className="text-sm font-medium text-win11-text-secondary mb-2">Generated Mermaid Source:</div>
                      <pre className="text-xs bg-win11-surface p-3 rounded border border-win11-border max-h-64 overflow-auto">
{normalizedMermaid || ''}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Resize Handle */}
            <div 
              className="absolute bottom-0 right-0 w-4 h-4 cursor-se-resize bg-gray-300 hover:bg-gray-400"
              style={{ 
                clipPath: 'polygon(100% 0%, 0% 100%, 100% 100%)'
              }}
              onMouseDown={handleResizeStart}
              title="Drag to resize"
            />
          </div>
        </div>
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
                    {/* For mermaid timeline, if rendered, we suppress raw cell display */}
                    {isMermaidTimeline && renderedMermaid && cellIndex === 0 ? (
                      <span className="text-xs italic text-win11-text-tertiary">(Rendered above)</span>
                    ) : expanded && typeof cell === 'string' && cell.length > 120 ? (
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