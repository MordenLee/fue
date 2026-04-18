import type { ReferenceItem } from '../../types/conversation'
import { FileText } from 'lucide-react'

interface CitationPopoverProps {
  reference: ReferenceItem
}

export function CitationPopover({ reference }: CitationPopoverProps) {
  return (
    <div className="space-y-2 max-w-xs">
      <div className="flex items-center gap-2">
        <FileText className="h-4 w-4 text-blue-400" />
        <span className="font-medium text-sm text-white">{reference.original_filename}</span>
      </div>
      <p className="text-xs text-neutral-400 leading-relaxed">{reference.formatted_citation}</p>
    </div>
  )
}
