import { getLanguage, t } from '../i18n'

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB'
}

export function formatDate(isoDate: string): string {
  const d = new Date(isoDate)
  const locale = getLanguage() === 'en' ? 'en-US' : 'zh-CN'
  return d.toLocaleDateString(locale, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function formatRelativeTime(isoDate: string): string {
  const now = Date.now()
  const diff = now - new Date(isoDate).getTime()
  const mins = Math.floor(diff / 60000)

  if (mins < 1) return t('time.just_now')
  if (mins < 60) return t('time.minutes_ago', { count: mins })
  const hours = Math.floor(mins / 60)
  if (hours < 24) return t('time.hours_ago', { count: hours })
  const days = Math.floor(hours / 24)
  if (days < 30) return t('time.days_ago', { count: days })
  return formatDate(isoDate)
}
