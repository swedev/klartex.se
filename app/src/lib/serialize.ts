/**
 * Tiptap-doc → klartex-JSON-block-array.
 *
 * Fas 1 täcker basblock-setet — heading, paragraph, bulletList, orderedList.
 * Custom klartex-block (signatures, agenda, …) implementeras i fas 2 som egna
 * Tiptap-noder; just nu ignoreras okända noder tyst.
 *
 * Inline-markup speglar kärnans `klartex/inline_markup.py` (markdown-likt):
 *   - bold   → `**text**`
 *   - italic → `*text*`
 *   - code   → `` `text` ``
 *   - link   → INTE i fas 1 (`inline_markup.py` har explicit `links: out of scope v1`)
 *
 * Rundresa-förlustfrihet är inte garanterad ännu — testsviten kommer i fas 2.
 */

export type KlartexHeading = { type: 'heading'; text: string; level: 1 | 2 | 3 }
export type KlartexText = { type: 'text'; text: string }
export type KlartexList = {
  type: 'list'
  style: 'bullet' | 'numbered'
  items: KlartexListItem[]
}
export type KlartexListItem = string | { text: string; content: KlartexBlock[] }
export type KlartexBlock = KlartexHeading | KlartexText | KlartexList

interface TiptapMark {
  type: string
}

interface TiptapNode {
  type: string
  attrs?: Record<string, unknown>
  content?: TiptapNode[]
  text?: string
  marks?: TiptapMark[]
}

/**
 * Konvertera en Tiptap-doc (ProseMirror-JSON) till klartex-JSON-block-array
 * lämplig för `POST /render` med `template: "_block"`.
 */
export function tiptapToKlartex(doc: TiptapNode): KlartexBlock[] {
  const blocks: KlartexBlock[] = []
  for (const node of doc.content ?? []) {
    const block = blockFromNode(node)
    if (block) blocks.push(block)
  }
  return blocks
}

function blockFromNode(node: TiptapNode): KlartexBlock | null {
  switch (node.type) {
    case 'heading': {
      const text = inlineText(node.content)
      if (!text) return null
      return { type: 'heading', text, level: clampLevel(node.attrs?.level) }
    }
    case 'paragraph': {
      const text = inlineText(node.content)
      if (!text) return null
      return { type: 'text', text }
    }
    case 'bulletList':
      return { type: 'list', style: 'bullet', items: listItems(node.content) }
    case 'orderedList':
      return { type: 'list', style: 'numbered', items: listItems(node.content) }
    default:
      // Unknown node → ignored. Fas 2 lägger till custom-noder.
      return null
  }
}

/**
 * Tiptap `listItem` innehåller paragrafer (och ev. nästlade listor).
 * Mappas till klartex-list-item: enkel sträng om bara en paragraf,
 * annars `{ text, content }` där content är de nästlade blocken.
 */
function listItems(items: TiptapNode[] = []): KlartexListItem[] {
  return items.flatMap((li): KlartexListItem[] => {
    if (li.type !== 'listItem') return []
    const children = li.content ?? []
    const paragraphs = children.filter((c) => c.type === 'paragraph')
    const nested = children
      .filter((c) => c.type === 'bulletList' || c.type === 'orderedList')
      .map(blockFromNode)
      .filter((b): b is KlartexBlock => b !== null)

    const text = paragraphs
      .map((p) => inlineText(p.content))
      .filter(Boolean)
      .join(' ')

    if (nested.length === 0) return [text]
    return [{ text, content: nested }]
  })
}

/**
 * Joina inline-noder med klartex-markdown-markup applicerad per Tiptap-mark.
 * Speglar `klartex/inline_markup.py` — bold före italic, code-spans skyddas.
 */
function inlineText(nodes: TiptapNode[] = []): string {
  let out = ''
  for (const n of nodes) {
    if (n.type === 'hardBreak') {
      out += '\n'
      continue
    }
    if (n.type !== 'text' || typeof n.text !== 'string') continue
    out += applyMarks(n.text, new Set((n.marks ?? []).map((m) => m.type)))
  }
  return out
}

function applyMarks(text: string, marks: Set<string>): string {
  // Wrappa inifrån och ut. Ordning spelar roll om vi någonsin börjar
  // tillåta nästlade marks i samma run; tills vidare wrappar vi en
  // gång per mark.
  let t = text
  if (marks.has('code')) t = `\`${t}\``
  if (marks.has('italic')) t = `*${t}*`
  if (marks.has('bold')) t = `**${t}**`
  return t
}

function clampLevel(level: unknown): 1 | 2 | 3 {
  const n = typeof level === 'number' ? level : 1
  if (n <= 1) return 1
  if (n >= 3) return 3
  return 2
}
