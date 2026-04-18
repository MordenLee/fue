import { Select } from '../ui/Select'
import { useI18n } from '../../i18n'

interface CitationStyleSelectProps {
  value: string
  onChange: (style: string) => void
  label?: string
  className?: string
}

export function CitationStyleSelect({ value, onChange, label, className }: CitationStyleSelectProps) {
  const { t } = useI18n()

  const citationStyles = [
    { value: 'apa', label: t('citation.style_apa') },
    { value: 'mla', label: t('citation.style_mla') },
    { value: 'chicago', label: t('citation.style_chicago') },
    { value: 'gb_t7714', label: t('citation.style_gb_t7714') }
  ]

  return (
    <Select
      value={value}
      onValueChange={onChange}
      options={citationStyles}
      label={label}
      placeholder={t('common.citation_style')}
      className={className}
    />
  )
}
