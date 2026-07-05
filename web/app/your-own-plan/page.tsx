import HomePageClient from '@/components/HomePageClient'
import { createClient } from '@/lib/supabase/server'
import type { Profile } from '@/lib/useUser'

export default async function YourOwnPlanPage() {
  const supabase = createClient()
  const { data: sessionData } = await supabase.auth.getSession()
  const user = sessionData.session?.user ?? null

  let profile: Profile | null = null
  if (user) {
    const { data: profileData } = await supabase
      .from('profiles')
      .select('id,email,plan_expires_at,custom_initial,custom_monthly,dca_enabled,dca_day_of_month')
      .eq('id', user.id)
      .maybeSingle()
    profile = (profileData as Profile | null) ?? null
  }

  return <HomePageClient initialUser={user} initialProfile={profile} pageVariant="plan" />
}
