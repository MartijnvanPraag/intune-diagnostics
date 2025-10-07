import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownRendererProps {
  content: string
  className?: string
}

/**
 * Renders markdown content with proper styling
 * Supports GitHub Flavored Markdown (tables, strikethrough, etc.)
 */
export default function MarkdownRenderer({ content, className = '' }: MarkdownRendererProps) {
  return (
    <div className={`prose prose-sm max-w-none ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Customize heading styles
          h1: ({ node, ...props }) => (
            <h1 className="text-2xl font-bold text-win11-text-primary mt-6 mb-4" {...props} />
          ),
          h2: ({ node, ...props }) => (
            <h2 className="text-xl font-semibold text-win11-text-primary mt-5 mb-3" {...props} />
          ),
          h3: ({ node, ...props }) => (
            <h3 className="text-lg font-medium text-win11-text-primary mt-4 mb-2" {...props} />
          ),
          h4: ({ node, ...props }) => (
            <h4 className="text-base font-medium text-win11-text-primary mt-3 mb-2" {...props} />
          ),
          // Customize paragraph styles
          p: ({ node, ...props }) => (
            <p className="text-win11-text-primary mb-3 leading-relaxed" {...props} />
          ),
          // Customize list styles
          ul: ({ node, ...props }) => (
            <ul className="list-disc list-inside text-win11-text-primary mb-3 space-y-1" {...props} />
          ),
          ol: ({ node, ...props }) => (
            <ol className="list-decimal list-inside text-win11-text-primary mb-3 space-y-1" {...props} />
          ),
          li: ({ node, ...props }) => (
            <li className="text-win11-text-primary ml-4" {...props} />
          ),
          // Customize code styles
          code: ({ node, className, children, ...props }) => {
            const isInline = !className?.includes('language-')
            if (isInline) {
              return (
                <code
                  className="bg-gray-100 dark:bg-gray-800 text-red-600 dark:text-red-400 px-1.5 py-0.5 rounded text-sm font-mono"
                  {...props}
                >
                  {children}
                </code>
              )
            }
            return (
              <code
                className="block bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100 p-3 rounded-md overflow-x-auto text-sm font-mono border border-gray-300 dark:border-gray-700"
                {...props}
              >
                {children}
              </code>
            )
          },
          // Customize pre (code block wrapper) styles
          pre: ({ node, ...props }) => (
            <pre
              className="bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100 rounded-md overflow-x-auto mb-4 border border-gray-300 dark:border-gray-700"
              {...props}
            />
          ),
          // Customize table styles
          table: ({ node, ...props }) => (
            <div className="overflow-x-auto mb-4">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700" {...props} />
            </div>
          ),
          thead: ({ node, ...props }) => (
            <thead className="bg-gray-50 dark:bg-gray-800" {...props} />
          ),
          tbody: ({ node, ...props }) => (
            <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700" {...props} />
          ),
          th: ({ node, ...props }) => (
            <th
              className="px-4 py-2 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider"
              {...props}
            />
          ),
          td: ({ node, ...props }) => (
            <td className="px-4 py-2 text-sm text-win11-text-primary whitespace-nowrap" {...props} />
          ),
          // Customize link styles
          a: ({ node, ...props }) => (
            <a
              className="text-win11-accent hover:text-win11-accent-hover underline"
              target="_blank"
              rel="noopener noreferrer"
              {...props}
            />
          ),
          // Customize blockquote styles
          blockquote: ({ node, ...props }) => (
            <blockquote
              className="border-l-4 border-win11-accent pl-4 py-2 italic text-gray-600 dark:text-gray-400 my-3"
              {...props}
            />
          ),
          // Customize horizontal rule
          hr: ({ node, ...props }) => (
            <hr className="border-t border-gray-300 dark:border-gray-700 my-4" {...props} />
          ),
          // Customize strong/bold
          strong: ({ node, ...props }) => (
            <strong className="font-semibold text-win11-text-primary" {...props} />
          ),
          // Customize emphasis/italic
          em: ({ node, ...props }) => (
            <em className="italic text-win11-text-primary" {...props} />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
