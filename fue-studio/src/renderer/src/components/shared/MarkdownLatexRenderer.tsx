import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import remarkGfm from 'remark-gfm'
import rehypeKatex from 'rehype-katex'
import rehypeHighlight from 'rehype-highlight'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/github-dark.min.css'
import { Copy, Check } from 'lucide-react'
import { useState } from 'react'
import { useI18n } from '../../i18n'

interface MarkdownLatexRendererProps {
  content: string
  isStreaming?: boolean
  className?: string
  onCiteClick?: (refNum: number) => void
  knownCiteRefs?: Set<number>
}

// ---------------------------------------------------------------------------
// Citation style constant (used in multiple components)
// ---------------------------------------------------------------------------
const CITE_SUP_CLASS = 'inline-flex items-center justify-center h-[16px] px-[3px] rounded bg-blue-500/15 text-[10px] font-bold text-blue-500 dark:text-blue-400 mx-[1px] no-underline select-none leading-none -top-1 relative'

function CodeBlock({ children, className }: { children: React.ReactNode; className?: string }) {
  const { t } = useI18n()
  const [copied, setCopied] = useState(false)
  const language = className?.replace('language-', '') ?? ''

  const handleCopy = () => {
    const text = String(children).replace(/\n$/, '')
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="relative group rounded-lg overflow-hidden my-3">
      <div className="flex items-center justify-between px-4 py-1.5 bg-neutral-800 border-b border-white/5 text-xs text-neutral-400">
        <span>{language}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-white transition opacity-0 group-hover:opacity-100"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? t('common.copied') : t('common.copy')}
        </button>
      </div>
      <pre className="!m-0 !rounded-none"><code className={className}>{children}</code></pre>
    </div>
  )
}

export function MarkdownLatexRenderer({ content, isStreaming, className = '', onCiteClick, knownCiteRefs }: MarkdownLatexRendererProps) {
  // ---------------------------------------------------------------------------
  // KEY FIX: Convert [N] / [CITE-N] to standard Markdown inline links.
  //
  // [1]  →  [1](#cite-1)
  // [CITE-2]  →  [2](#cite-2)
  // [1][2]  →  [1](#cite-1)[2](#cite-2)  (two separate inline links)
  //
  // `react-markdown` filters custom protocols like `cite:` by default, so
  // we use safe hash links and intercept them in the custom `a` renderer.
  // ---------------------------------------------------------------------------
  const processedContent = useMemo(() => {
    return content.replace(
      /\[(?:CITE-)?(\d+)\](?!\(#cite-\d+\))/g,
      (_, n) => `[${n}](#cite-${n})`
    )
  }, [content])

  const remarkPlugins = useMemo(
    () => (isStreaming ? [remarkGfm] : [remarkMath, remarkGfm]),
    [isStreaming]
  )
  const rehypePlugins = useMemo(
    () => (
      isStreaming
        ? [rehypeHighlight]
        : [[rehypeKatex, { throwOnError: false, strict: 'ignore' }], rehypeHighlight]
    ),
    [isStreaming]
  )

  return (
    <div className={`markdown-body prose prose-invert prose-sm max-w-none overflow-x-hidden
      prose-pre:bg-neutral-900 prose-pre:p-0
      prose-code:before:hidden prose-code:after:hidden
      prose-code:bg-white/10 prose-code:rounded prose-code:px-1.5 prose-code:py-0.5 prose-code:text-xs
      prose-table:border-white/10
      prose-th:border-white/10 prose-th:bg-white/5 prose-th:px-3 prose-th:py-2
      prose-td:border-white/10 prose-td:px-3 prose-td:py-2
      prose-blockquote:border-blue-500/50
      prose-a:text-blue-400
      prose-headings:text-white
      ${isStreaming ? 'streaming' : ''} ${className}`}
    >
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins as never[]}
        components={{
          code({ className: cn, children, ...props }) {
            const isBlock = cn?.startsWith('language-')
            if (isBlock) {
              return <CodeBlock className={cn}>{children}</CodeBlock>
            }
            return <code className={cn} {...props}>{children}</code>
          },
          pre({ children }) {
            return <>{children}</>
          },
          a({ href, children }) {
            if (href?.startsWith('#cite-')) {
              const num = parseInt(href.slice(6))
              if (!isNaN(num)) {
                const isKnown = !knownCiteRefs || knownCiteRefs.has(num)
                return (
                  <button
                    type="button"
                    onClick={() => isKnown && onCiteClick?.(num)}
                    className={CITE_SUP_CLASS}
                    title={`引用 [${num}]`}
                    aria-label={`引用 ${num}`}
                  >
                    [{num}]
                  </button>
                )
              }
            }
            return <a href={href} target="_blank" rel="noreferrer">{children}</a>
          }
        }}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  )
}
