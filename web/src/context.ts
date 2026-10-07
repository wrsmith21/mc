import { createContext, useContext } from 'react'
import type { Json } from './api'

export type AppState = {
  meta: Json | null
  persona: string
  setPersona: (id: string) => void
  toast: (msg: string, kind?: 'ok' | 'error') => void
  bump: () => void
  version: number
  pace: number
}

export const AppCtx = createContext<AppState>({
  meta: null, persona: 'E34120', setPersona: () => {}, toast: () => {}, bump: () => {}, version: 0, pace: 1,
})

export const useApp = () => useContext(AppCtx)

export const personName = (meta: Json | null, id: string) =>
  meta?.personas?.find((p: Json) => p.id === id)?.name ?? id
