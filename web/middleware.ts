import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value),
          )
          response = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options),
          )
        },
      },
    },
  )

  try {
    // Refresh the session, but never let a slow or unreachable auth backend
    // block the page (2026-07-05: paused Supabase project made every
    // cookie-carrying request 504 via MIDDLEWARE_INVOCATION_TIMEOUT).
    await Promise.race([
      supabase.auth.getUser(),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('auth refresh timeout')), 5000),
      ),
    ])
  } catch {
    // Fail open: serve the page unauthenticated.
  }
  return response
}

export const config = {
  // Only routes that actually use the session. The research-note homepage is
  // static and must not depend on Supabase availability.
  matcher: ['/your-own-plan/:path*', '/auth/:path*'],
}
