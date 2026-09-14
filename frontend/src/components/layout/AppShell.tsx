'use client'

import TopHeader from './TopHeader'
import SideNav from './SideNav'

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-screen flex flex-col overflow-hidden bg-brand-bg text-slate-200 font-sans antialiased relative z-10">
      <TopHeader />
      <div className="flex-1 flex overflow-hidden">
        <SideNav />
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
