import { useState } from 'react'
import { api } from '../api'
import { brand } from '../brand'

export default function Login({ onDone }: { onDone: () => void }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  return (
    <div className="center-page">
      <form className="login" onSubmit={async (e) => {
        e.preventDefault()
        try {
          await api.login(code)
          onDone()
        } catch {
          setError('That passcode is not right. Check the one shared for this session.')
        }
      }}>
        {brand.logo && <img src={brand.logo} alt={brand.client} />}
        <h2 style={{ marginTop: 14 }}>{brand.product}</h2>
        <p className="muted small">{brand.disclaimer}</p>
        <input type="password" placeholder="Session passcode" value={code} onChange={(e) => setCode(e.target.value)} autoFocus aria-label="Session passcode" />
        {error && <p className="small" style={{ color: 'var(--red-ink)', marginBottom: 10 }}>{error}</p>}
        <button className="btn primary" type="submit">Open the demo</button>
      </form>
    </div>
  )
}
