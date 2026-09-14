import type { Metadata } from 'next'
import './globals.css'
import ToastProvider from '@/components/ui/ToastNotification'

export const metadata: Metadata = {
  title: 'SPYDER-DETECT | Criminal Intelligence Platform',
  description: 'Secure evidence graph analysis and investigation platform',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full bg-[#070D14]">
      <body className="h-full">
        <ToastProvider>
          {children}
        </ToastProvider>
      </body>
    </html>
  )
}
