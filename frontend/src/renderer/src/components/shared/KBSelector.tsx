import { useState, useEffect } from 'react'
import { MultiSelect } from '../ui/MultiSelect'
import { knowledgeService } from '../../services/knowledge'
import type { KnowledgeBaseOut } from '../../types/knowledge'
import { useI18n } from '../../i18n'

interface KBSelectorProps {
  value: number[]
  onChange: (kbIds: number[]) => void
  label?: string
  placeholder?: string
}

export function KBSelector({ value, onChange, label, placeholder }: KBSelectorProps) {
  const { t } = useI18n()
  const [kbs, setKbs] = useState<KnowledgeBaseOut[]>([])

  useEffect(() => {
    knowledgeService.list().then(setKbs).catch(console.error)
  }, [])

  const options = kbs.map((kb) => ({
    value: String(kb.id),
    label: `${kb.name} (${kb.document_count})`
  }))

  return (
    <MultiSelect
      options={options}
      value={value.map(String)}
      onChange={(vals) => onChange(vals.map(Number))}
      label={label}
      placeholder={placeholder ?? t('common.select_kb')}
    />
  )
}
