import { createContext, useContext } from 'react'
import type { Json } from './api'

export type Session = {
  person: Json
  roles: string[]
  role_labels: string[]
  can: string[]
}

export type AppState = {
  meta: Json | null
  session: Session | null
  switchUser: () => void
  toast: (msg: string, kind?: 'ok' | 'error') => void
  bump: () => void
  version: number
  /** Presentation pace: the client spaces out events it has already received. The agent itself never waits. */
  slow: boolean
}

export const AppCtx = createContext<AppState>({
  meta: null, session: null, switchUser: () => {}, toast: () => {}, bump: () => {}, version: 0, slow: false,
})

export const useApp = () => useContext(AppCtx)

export const useCan = () => {
  const { session } = useApp()
  return (action: string) => !!session?.can.includes(action)
}

export const personName = (meta: Json | null, id: string) =>
  meta?.personas?.find((p: Json) => p.id === id)?.name ?? id
