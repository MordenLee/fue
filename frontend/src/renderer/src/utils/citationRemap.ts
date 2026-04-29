/**
 * Citation display remapping utilities.
 *
 * The backend always stores raw chunk-based CITE-N sequential numbers that are
 * globally unique across turns (thanks to the initial_cite_num offset).
 * The frontend then applies a display remapping at render time based on the
 * current chat_citation_mode setting:
 *
 *   chunk mode   — each unique chunk gets a sequential display number 1, 2, 3 …
 *                  The reference list groups by document and shows all chunk numbers.
 *   document mode — each unique document gets a sequential display number 1, 2, 3 …
 *                  All chunks from the same document share that single display number.
 *
 * Remapping is computed globally across ALL conversation turns so that:
 *  - Numbers are contiguous (1, 2, 3 — no gaps).
 *  - Previously seen documents / chunks keep their assigned numbers in later turns.
 *  - New items continue from the current maximum.
 */

import type { ReferenceItem } from '../types/conversation'

export interface RefDisplayMap {
  /** originalRefNum → displayNum  (for substituting [N] in message text) */
  localToDisplay: Map<number, number>
  /** displayNum → list of originalRefNums  (reverse lookup for click handlers) */
  displayToLocals: Map<number, number[]>
}

/**
 * Build a per-message display mapping from all messages' references combined.
 *
 * Messages are processed in order so earlier turns get lower display numbers.
 * Returns a Map keyed by message id (streaming placeholder id = -1).
 */
export function buildGlobalCitationRemapping(
  messages: Array<{ id: number; references: ReferenceItem[] | null }>,
  streamingRefs: ReferenceItem[] | null,
  citationMode: 'document' | 'chunk'
): Map<number, RefDisplayMap> {
  // Document mode: persistent map so the same doc keeps its display number
  const docToDisplayNum = new Map<number, number>()
  let nextDocNum = 1

  // Chunk mode: global counter across all turns
  let globalChunkCounter = 0

  const result = new Map<number, RefDisplayMap>()

  const processMessage = (msgId: number, refs: ReferenceItem[]) => {
    const sorted = [...refs].sort((a, b) => a.ref_num - b.ref_num)
    const localToDisplay = new Map<number, number>()

    if (citationMode === 'document') {
      // Collect unique docs in first-appearance order within this message
      const docOrder: number[] = []
      const seenDocs = new Set<number>()
      for (const ref of sorted) {
        if (!seenDocs.has(ref.document_file_id)) {
          seenDocs.add(ref.document_file_id)
          docOrder.push(ref.document_file_id)
        }
      }
      // Assign global display numbers to docs that haven't been seen yet
      for (const docId of docOrder) {
        if (!docToDisplayNum.has(docId)) {
          docToDisplayNum.set(docId, nextDocNum++)
        }
      }
      // Map each local chunk ref_num to its document's global display number
      for (const ref of sorted) {
        localToDisplay.set(ref.ref_num, docToDisplayNum.get(ref.document_file_id)!)
      }
    } else {
      // Chunk mode: each unique local ref_num gets the next global display number
      const seenLocalRefs = new Set<number>()
      for (const ref of sorted) {
        if (!seenLocalRefs.has(ref.ref_num)) {
          seenLocalRefs.add(ref.ref_num)
          globalChunkCounter++
          localToDisplay.set(ref.ref_num, globalChunkCounter)
        }
      }
    }

    // Build reverse map: displayNum → [originalRefNums]
    const displayToLocals = new Map<number, number[]>()
    for (const [local, display] of localToDisplay.entries()) {
      if (!displayToLocals.has(display)) displayToLocals.set(display, [])
      displayToLocals.get(display)!.push(local)
    }

    result.set(msgId, { localToDisplay, displayToLocals })
  }

  for (const msg of messages) {
    if (msg.references && msg.references.length > 0) {
      processMessage(msg.id, msg.references)
    }
  }

  if (streamingRefs && streamingRefs.length > 0) {
    processMessage(-1, streamingRefs)
  }

  return result
}

/**
 * Replace [N] citation markers in message text with their display numbers.
 * Processes entries in descending original-number order to avoid partial
 * replacement (e.g., replacing "[1]" inside "[10]").
 */
export function applyRefRemapping(content: string, localToDisplay: Map<number, number>): string {
  if (localToDisplay.size === 0) return content
  const entries = [...localToDisplay.entries()].sort((a, b) => b[0] - a[0])
  let text = content
  for (const [local, display] of entries) {
    if (local === display) continue
    // Replace [N] not already converted to [N](#cite-N) by MarkdownLatexRenderer
    text = text.replace(new RegExp(`\\[${local}\\](?!\\(#cite-)`, 'g'), `[${display}]`)
  }
  // Deduplicate adjacent identical citation markers that arise when multiple
  // chunks of the same document are mapped to the same display number.
  // e.g. "[2] [2]" → "[2]",  "[2][2][2]" → "[2]"
  text = text.replace(/(\[\d+\])(\s*\1)+/g, '$1')
  return text
}

/**
 * Return a copy of the references array with ref_num replaced by display numbers.
 */
export function remapRefNums(
  refs: ReferenceItem[],
  localToDisplay: Map<number, number>
): ReferenceItem[] {
  return refs.map(ref => ({
    ...ref,
    ref_num: localToDisplay.get(ref.ref_num) ?? ref.ref_num,
  }))
}
