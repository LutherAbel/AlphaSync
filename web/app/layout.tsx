import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'AlphaSync : Your reliable quant engine',
  description: 'Weekly momentum signals with capital-scaled allocation sync.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-TW">
      <body>
        <div className="container">{children}</div>
      </body>
    </html>
  )
}
