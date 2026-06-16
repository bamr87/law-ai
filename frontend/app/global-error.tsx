'use client'

/** Last-resort boundary if the root layout itself throws (must render <html>). */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <html lang="en">
      <body
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#090d17',
          color: '#eaf0fb',
          fontFamily: 'system-ui, sans-serif',
        }}
      >
        <div style={{ textAlign: 'center', padding: 24 }}>
          <h1 style={{ fontSize: 18, fontWeight: 600 }}>
            LawGraph AI hit a fatal error
          </h1>
          <p style={{ marginTop: 8, color: '#9fabc7', fontSize: 14 }}>
            {error.message || 'The application failed to render.'}
          </p>
          <button
            onClick={reset}
            style={{
              marginTop: 16,
              padding: '8px 16px',
              borderRadius: 8,
              background: '#5b7cfa',
              color: '#fff',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  )
}
