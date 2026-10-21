export function parseCiteMarkers(text: string, citeMap: Record<string, string>): string {
  // Handle both [CITE-1] and comma-separated [CITE-1, CITE-3] formats
  return text.replace(/\[CITE-\d+(?:\s*,\s*CITE-\d+)*\]/g, (match) => {
    // Check if it's a single [CITE-N]
    if (citeMap[match]) return citeMap[match]
    // Otherwise split comma-separated: [CITE-1, CITE-3] -> [1][3]
    const individual = [...match.matchAll(/CITE-(\d+)/g)]
    if (individual.length > 1) {
      return individual
        .map(m => {
          const key = `[CITE-${m[1]}]`
          return citeMap[key] ?? key
        })
        .join('')
    }
    return match
  })
}

export function extractCiteNumbers(text: string): number[] {
  const matches = text.matchAll(/\[(\d+)\]/g)
  return [...new Set([...matches].map((m) => Number(m[1])))]
}
