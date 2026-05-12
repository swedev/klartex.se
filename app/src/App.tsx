import { Box, Button, Callout, Container, Flex, Heading, Text } from '@radix-ui/themes'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { AlertTriangle, Download } from 'lucide-react'
import { useState } from 'react'

import { tiptapToKlartex } from './lib/serialize'

// I dev går /api genom Vite-proxyn (vite.config.ts). I prod är appen på
// app.klartex.se och anropar api.klartex.se direkt (Caddy CORS).
const API_BASE = import.meta.env.DEV ? '/api' : 'https://api.klartex.se'

function App() {
  const editor = useEditor({
    extensions: [StarterKit],
    content: '<h1>Min första klartex-PDF</h1><p>Skriv något här …</p>',
  })

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleRender = async () => {
    if (!editor) return
    setBusy(true)
    setError(null)
    try {
      const body = tiptapToKlartex(editor.getJSON())
      if (body.length === 0) {
        throw new Error('Editorn är tom — skriv något innan du renderar.')
      }
      const res = await fetch(`${API_BASE}/render`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template: '_block',
          data: { lang: 'sv', body },
          page_template: 'vkf',
        }),
      })

      if (!res.ok) {
        // FastAPI returnerar {"detail": {"type": "...", "message": "..."}}
        // — visa message direkt; fullständig översättning till svenska
        // kommer i fas 6.
        const txt = await res.text()
        let msg = txt
        try {
          const parsed: unknown = JSON.parse(txt)
          if (
            parsed && typeof parsed === 'object' && 'detail' in parsed
            && parsed.detail && typeof parsed.detail === 'object'
            && 'message' in parsed.detail
            && typeof parsed.detail.message === 'string'
          ) {
            msg = parsed.detail.message
          }
        } catch { /* not JSON, fall through */ }
        throw new Error(`API svarade ${res.status}: ${msg}`)
      }

      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'klartex.pdf'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Container size="3" my="6">
      <Flex direction="column" gap="4">
        <Heading size="6">klartex.se</Heading>
        <Text color="gray" size="2">
          Minimal editor (fas 1) — basblock: rubrik, paragraf, listor. Klicka
          "Ladda ner PDF" för att rendera med VKF-branding via{' '}
          <code>api.klartex.se/render</code>.
        </Text>
        <Box
          style={{
            border: '1px solid var(--gray-a5)',
            borderRadius: 'var(--radius-3)',
            padding: 'var(--space-4)',
            minHeight: '20em',
          }}
        >
          <EditorContent editor={editor} />
        </Box>
        {error && (
          <Callout.Root color="red">
            <Callout.Icon>
              <AlertTriangle size={16} />
            </Callout.Icon>
            <Callout.Text>{error}</Callout.Text>
          </Callout.Root>
        )}
        <Flex justify="end">
          <Button onClick={handleRender} disabled={busy} size="3">
            <Download size={16} />
            {busy ? 'Renderar …' : 'Ladda ner PDF'}
          </Button>
        </Flex>
      </Flex>
    </Container>
  )
}

export default App
