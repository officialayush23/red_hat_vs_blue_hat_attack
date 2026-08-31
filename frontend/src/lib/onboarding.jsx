import { createContext, useContext, useEffect, useMemo, useState } from "react"

const OnboardingContext = createContext(null)
const STORAGE_KEY = "fraudshield-onboarding-seen"

export function OnboardingProvider({ children }) {
  const [isOpen, setIsOpen] = useState(false)

  useEffect(() => {
    let seen = false
    try {
      seen = localStorage.getItem(STORAGE_KEY) === "true"
    } catch {
      // if storage is unavailable, default to showing the guide once per session
    }
    if (!seen) setIsOpen(true)
  }, [])

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
