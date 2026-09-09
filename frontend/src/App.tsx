import { useEffect, useState } from 'react'

// Placeholder shell. Routing and pages arrive once the app idea is chosen.
// The /health fetch below just proves the frontend can reach the backend.
export default function App() {
  const [backendStatus, setBackendStatus] = useState('checking...')

  useEffect(() => {
    fetch('/health')
      .then((res) => res.json())
      .then((data) => setBackendStatus(data.status ?? 'unknown'))
      .catch(() => setBackendStatus('unreachable'))
  }, [])

  return (
    <>
      <h1>INF2003 Project</h1>
      <p>Backend: {backendStatus}</p>
    </>
  )
}
