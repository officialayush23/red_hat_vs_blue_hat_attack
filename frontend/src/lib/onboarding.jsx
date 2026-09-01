import { createContext, useContext, useMemo, useState } from "react"

const OnboardingContext = createContext(null)
const STORAGE_KEY = "fraudshield-onboarding-seen"

function hasSeenGuide() {
  try {
    return localStorage.getItem(STORAGE_KEY) === "true"
  } catch {
    // Storage unavailable (private mode, blocked site data). Showing the guide
    // once per session is the right failure mode -- better than suppressing it
    // for someone who has never seen it.
    return false
  }
}

export function OnboardingProvider({ children }) {
  // Lazy initialiser, NOT an effect. Reading storage in useEffect meant the
  // first paint always rendered isOpen=false and then immediately set it true,
  // so a returning user could see the guide flash open and shut, and every
  // mount cost an extra render pass. The value is known before the first
  // render, so it belongs in the initial state.
  const [isOpen, setIsOpen] = useState(() => !hasSeenGuide())

  const value = useMemo(
    () => ({
      isOpen,
      open: () => setIsOpen(true),
      close: () => {
        setIsOpen(false)
        try {
          localStorage.setItem(STORAGE_KEY, "true")
        } catch {
          // best-effort persistence only
        }
      },
    }),
    [isOpen]
  )

  return <OnboardingContext.Provider value={value}>{children}</OnboardingContext.Provider>
}

export function useOnboarding() {
  const ctx = useContext(OnboardingContext)
  if (!ctx) throw new Error("useOnboarding must be used within an <OnboardingProvider />")
  return ctx
}
