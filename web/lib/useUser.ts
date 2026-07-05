'use client'

import { useEffect, useState } from 'react'
import type { User } from '@supabase/supabase-js'
import { createClient } from '@/lib/supabase/client'

export type Profile = {
  id: string
  email: string | null
  plan_expires_at: string | null
  custom_initial: number | null
  custom_monthly: number | null
  dca_enabled: boolean | null
  dca_day_of_month: number | null
}

export function useUser(initialUser: User | null = null, initialProfile: Profile | null = null) {
  const [user, setUser] = useState<User | null>(initialUser)
  const [profile, setProfile] = useState<Profile | null>(initialProfile)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const supabase = createClient()
    let active = true

    async function syncProfile(sessionUser: User | null) {
      if (!active) return
      setUser(sessionUser)
      if (sessionUser) {
        const { data: profileData, error: profileErr } = await supabase
          .from('profiles')
          .select('id,email,plan_expires_at,custom_initial,custom_monthly,dca_enabled,dca_day_of_month')
          .eq('id', sessionUser.id)
          .maybeSingle()
        if (active) setProfile((profileData as Profile | null) ?? null)
      } else {
        setProfile(null)
      }
      if (active) setLoading(false)
    }

    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      void syncProfile(session?.user ?? null)
    })
    return () => {
      active = false
      sub.subscription.unsubscribe()
    }
  }, [])

  return { user, profile, loading }
}
