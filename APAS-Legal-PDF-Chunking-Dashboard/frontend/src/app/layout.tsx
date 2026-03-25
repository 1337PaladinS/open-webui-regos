import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Legal PDF Chunking Dashboard',
  description: 'Upload, analyze, chunk, and push legal PDFs to Neo4j',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-dark-900 text-dark-50 antialiased">
        {children}
      </body>
    </html>
  )
}
