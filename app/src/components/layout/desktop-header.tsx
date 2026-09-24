import { useIsFetching } from '@tanstack/react-query'
import { Link, useNavigate, useRouterState } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { NotificationBell } from '@/features/notify/notification-bell'
import { SearchField } from '@/features/search/search-screen'
import { useSearchAbilities } from '@/features/search/use-search'

/**
 * 76 px header: the search field on the left, notifications on the right. Muninn reads the
 * NAS and has no upload, so the design's upload button is left out.
 *
 * No page title: the sidebar already says where you are, and the photos start higher up without
 * a headline repeating it. Screen readers keep the page name through the heading in the shell.
 */
/** The search field of every page: it starts a search, and on the search page it shows it. */
function HeaderSearch() {
  const navigate = useNavigate()
  const abilities = useSearchAbilities()
  const looking = useIsFetching({ queryKey: ['media', 'search'] })
  const current = useRouterState({
    select: (state) => {
      if (state.location.pathname !== '/search') return ''
      // "2012" alone arrives as a number: a query string has no types.
      const q = (state.location.search as { q?: unknown }).q
      return typeof q === 'string' || typeof q === 'number' ? String(q) : ''
    },
  })

  return (
    <SearchField
      key={current}
      initial={current}
      className="max-w-[520px] flex-1"
      ai={abilities.data?.ready === true}
      busy={looking > 0}
      onSearch={(words) => {
        void navigate({ to: '/search', search: { q: words } })
      }}
    />
  )
}

export function DesktopHeader() {
  const { t } = useTranslation()
  return (
    <header className="hidden h-[76px] shrink-0 items-center gap-6 border-b border-hairline/[0.08] px-8 md:flex">
      <HeaderSearch />
      {/* The search has no place in the sidebar: the field is here, and the page with its
          persons, filters and hints is one step further. */}
      <Link
        to="/search"
        className="-ml-3 flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-2 text-sm-plus font-medium text-muted-foreground transition hover:bg-secondary hover:text-foreground data-[status=active]:text-primary"
      >
        <Symbol name="tune" size={18} />
        {t('header.advancedSearch')}
      </Link>

      <div className="ml-auto flex items-center gap-2">
        <NotificationBell />
      </div>
    </header>
  )
}
