import { Box, Container, Flex, Heading, Text } from '@radix-ui/themes'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'

// Fas 1, första steg: bara mounted Tiptap-editor. Submit till
// /render och Tiptap → klartex-JSON-serialisering kommer i följande
// commits. Detta steg verifierar att stacken bygger och att Tiptap
// renderas korrekt med Radix Themes runtomkring.
function App() {
  const editor = useEditor({
    extensions: [StarterKit],
    content: '<h1>Min första klartex-PDF</h1><p>Skriv något här …</p>',
  })

  return (
    <Container size="3" my="6">
      <Flex direction="column" gap="4">
        <Heading size="6">klartex.se</Heading>
        <Text color="gray" size="2">
          Minimal editor (fas 1). Submit-knapp och PDF-nedladdning kommer i
          följande commits.
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
      </Flex>
    </Container>
  )
}

export default App
