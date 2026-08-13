import { FolderKanban, LayoutDashboard, LogOut, ScanLine } from 'lucide-react'
import { Link, NavLink } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/lib/utils'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
    isActive ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:text-foreground',
  )

/**
 * Shared header for authenticated pages: brand, workspace navigation, and
 * sign out. Keeps the dashboard/projects pages visually consistent.
 */
export function AppHeader() {
  const { signOut } = useAuth()

  return (
    <header className="border-b">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-6">
          <Link to="/dashboard" className="flex items-center gap-2 font-semibold tracking-tight">
            <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <ScanLine className="size-4" aria-hidden="true" />
            </span>
            a11y-framework
          </Link>
          <nav aria-label="Main" className="flex items-center gap-1">
            <NavLink to="/dashboard" className={navLinkClass}>
              <LayoutDashboard className="size-4" aria-hidden="true" />
              Dashboard
            </NavLink>
            <NavLink to="/projects" className={navLinkClass}>
              <FolderKanban className="size-4" aria-hidden="true" />
              Projects
            </NavLink>
          </nav>
        </div>
        <Button variant="outline" size="sm" onClick={() => void signOut()}>
          <LogOut className="size-4" aria-hidden="true" />
          Sign out
        </Button>
      </div>
    </header>
  )
}
