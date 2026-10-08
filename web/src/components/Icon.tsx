const PATHS: Record<string, string> = {
  inbox: 'M3 13h4l1.5 2.5h7L17 13h4M5 5h14l2 8v5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-5z',
  queue: 'M4 6h16M4 12h16M4 18h10',
  close: 'M4 19V9m6 10V5m6 14v-7m4 7H3',
  value: 'M4 17l5-5 4 4 7-8M15 8h5v5',
  model: 'M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5',
  arch: 'M4 4h6v6H4zM14 14h6v6h-6zM14 4h6v6h-6zM7 10v4h7',
  policy: 'M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z',
  audit: 'M8 4h8l3 3v13H5V4h3zM9 12h6M9 16h6M9 8h3',
  ops: 'M3 12h4l3-7 4 14 3-7h4',
  phone: 'M8 3h8a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM11 18h2',
  play: 'M8 5v14l11-7z',
  upload: 'M12 16V4m0 0l-4 4m4-4l4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3',
  clock: 'M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z',
  reset: 'M4 12a8 8 0 1 0 2.5-5.8M4 4v4h4',
}

export default function Icon({ name }: { name: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  )
}
