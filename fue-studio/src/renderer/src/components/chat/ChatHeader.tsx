import { ModelSelector } from '../shared/ModelSelector'
import { KBSelector } from '../shared/KBSelector'
import { CitationStyleSelect } from '../shared/CitationStyleSelect'
import { useI18n } from '../../i18n'

interface ChatHeaderProps {
  modelId: number | null
  onModelChange: (id: number | null) => void
  kbIds: number[]
  onKBChange: (ids: number[]) => void
  citationStyle: string
  onCitationStyleChange: (style: string) => void
}

export function ChatHeader({
  modelId, onModelChange, kbIds, onKBChange, citationStyle, onCitationStyleChange
}: ChatHeaderProps) {
  const { t } = useI18n()

  return (
    <div className="flex items-center gap-4 px-4 py-2.5 border-b border-white/10 shrink-0">
      <div className="w-48">
        <ModelSelector value={modelId} onChange={onModelChange} modelType="chat" placeholder={t('common.select_model')} />
      </div>
      <div className="w-56">
        <KBSelector value={kbIds} onChange={onKBChange} placeholder={t('chat.bind_kb')} />
      </div>
      {kbIds.length > 0 && (
        <div className="w-48">
          <CitationStyleSelect value={citationStyle} onChange={onCitationStyleChange} />
        </div>
      )}
    </div>
  )
}
