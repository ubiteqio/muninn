/** The pages to offer as numbers: the first, the last, and the ones around the current one. */
export function pagesAround(page: number, pages: number): (number | 'gap')[] {
  const wanted = new Set([1, pages, page - 1, page, page + 1].filter((n) => n >= 1 && n <= pages))
  const sorted = [...wanted].sort((a, b) => a - b)
  const shown: (number | 'gap')[] = []
  for (const number of sorted) {
    const last = shown.at(-1)
    if (typeof last === 'number' && number - last > 1) {
      // A gap of one page is shown as that page: "1 2 3" reads better than "1 … 3".
      if (number - last === 2) shown.push(last + 1)
      else shown.push('gap')
    }
    shown.push(number)
  }
  return shown
}
