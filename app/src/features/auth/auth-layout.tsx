import type { ReactNode } from 'react'

import { Knotwork } from '@/components/muninn/knotwork'

/**
 * The frame shared by signing in and setting a password.
 *
 * The handoff does not design these screens yet, so this is built from its tokens and patterns:
 * Rabenschwarz ground, a Mitternacht card, Cinzel for the name, knotwork as the only ornament.
 * The full wordmark is dark navy, hence the parchment tile behind it.
 */
export function AuthLayout({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <div className="flex min-h-full items-center justify-center bg-background px-5 py-10">
      <div className="w-full max-w-[380px]">
        <div className="flex flex-col items-center">
          <span className="rounded-mark-lg border border-[#EDE6D6]/50 bg-[#EDE6D6] px-5 py-3">
            <img src="/muninn-logo.png" alt="Muninn" className="h-10 w-auto object-contain" />
          </span>
          <Knotwork className="mt-5 w-20" />
        </div>

        <div className="mt-6 rounded-lg border border-hairline/[0.07] bg-card p-6">
          {/*
            Inter, not Cinzel: the handoff reserves Cinzel for the app name and large titles, and
            the app name is already above this card as the wordmark. A Cinzel heading right on top
            of an Inter sentence reads as two typefaces colliding.
          */}
          <h1 className="text-lg font-semibold text-foreground">{title}</h1>
          <p className="mt-1.5 text-base text-muted-foreground">{description}</p>
          {children}
        </div>
      </div>
    </div>
  )
}
