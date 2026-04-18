import { useLocation, useNavigate } from 'react-router-dom'
import { MessageSquare, Search, Library, Plug, Settings, Sun, Moon } from 'lucide-react'
import { NavButton } from '../ui/NavButton'
import { useSettings } from '../../contexts/SettingsContext'
import { useI18n } from '../../i18n'

const topNavItems = [
  { to: '/', icon: MessageSquare, key: 'nav.chat' },
  { to: '/search', icon: Search, key: 'nav.search' },
  { to: '/knowledge', icon: Library, key: 'nav.knowledge' }
]

const bottomNavItems = [
  { to: '/providers', icon: Plug, key: 'nav.providers' },
  { to: '/settings', icon: Settings, key: 'nav.settings' }
]

export function NavBar() {
  const { theme, toggleTheme } = useSettings()
  const { t } = useI18n()
  const location = useLocation()
  const navigate = useNavigate()

  const isActive = (to: string) =>
    to === '/' ? location.pathname === '/' : location.pathname.startsWith(to)

  return (
    <nav className="flex flex-col items-center w-16 shrink-0 border-r border-neutral-200 dark:border-white/10 bg-neutral-50 dark:bg-neutral-950 pt-4 pb-8">
      <div className="flex flex-col items-center gap-4">
        {topNavItems.map(({ to, icon: Icon, key }) => (
          <NavButton
            key={to}
            icon={<Icon className="h-5 w-5" />}
            tooltip={t(key)}
            isActive={isActive(to)}
            onClick={() => navigate(to)}
          />
        ))}
      </div>

      <div className="mt-auto flex flex-col items-center gap-4">
        <NavButton
          icon={theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          tooltip={theme === 'dark' ? t('nav.theme_to_light') : t('nav.theme_to_dark')}
          onClick={toggleTheme}
        />
        {bottomNavItems.map(({ to, icon: Icon, key }) => (
          <NavButton
            key={to}
            icon={<Icon className="h-5 w-5" />}
            tooltip={t(key)}
            isActive={isActive(to)}
            onClick={() => navigate(to)}
          />
        ))}
      </div>
    </nav>
  )
}

