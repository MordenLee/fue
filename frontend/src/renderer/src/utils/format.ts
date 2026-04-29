import { getLanguage, t } from '../i18n'

function parseApiDate(input: string): Date {
  const value = (input || '').trim()
  if (!value) return new Date(NaN)

  // Backend may emit naive UTC datetimes like:
  // 2026-04-28T10:00:00 or 2026-04-28 10:00:00
  // If timezone suffix is missing, treat it as UTC.
  const normalized = value.includes(' ') ? value.replace(' ', 'T') : value
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized)
  return new Date(hasTimezone ? normalized : `${normalized}Z`)
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB'
}

export function formatDate(isoDate: string): string {
  const d = parseApiDate(isoDate)
  if (Number.isNaN(d.getTime())) return t('common.neutral')
  const locale = getLanguage() === 'en' ? 'en-US' : 'zh-CN'
  return d.toLocaleDateString(locale, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function formatRelativeTime(isoDate: string): string {
  const ts = parseApiDate(isoDate).getTime()
  if (Number.isNaN(ts)) return t('common.neutral')
  const now = Date.now()
  const diff = Math.max(0, now - ts)
  const mins = Math.floor(diff / 60000)

  if (mins < 1) return t('time.just_now')
  if (mins < 60) return t('time.minutes_ago', { count: mins })
  const hours = Math.floor(mins / 60)
  if (hours < 24) return t('time.hours_ago', { count: hours })
  const days = Math.floor(hours / 24)
  if (days < 30) return t('time.days_ago', { count: days })
  return formatDate(isoDate)
}
