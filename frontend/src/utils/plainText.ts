/** Convert common Markdown emitted by OCR services into readable plain text. */
export function markdownToPlainText(markdown: string): string {
  const withoutBlocks = markdown
    .replace(/\r\n?/g, "\n")
    .replace(/^\s*```[^\n]*$/gm, "")
    .replace(/^\s*~~~[^\n]*$/gm, "")
    .replace(/^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$/gm, "")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s{0,3}>\s?/gm, "")
    .replace(/^\s*[-+*]\s+/gm, "• ")
    .replace(/^\s*([-*_])(?:\s*\1){2,}\s*$/gm, "");

  return withoutBlocks
    .split("\n")
    .map((line) => {
      const trimmed = line.trim();
      if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
        return trimmed.slice(1, -1).replace(/\s*\|\s*/g, "    ");
      }
      return line;
    })
    .join("\n")
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1 ($2)")
    .replace(/(\*\*|__|~~)(.*?)\1/g, "$2")
    .replace(/`([^`\n]+)`/g, "$1")
    .replace(/(^|[\s(])[*_]([^*_\n]+)[*_](?=$|[\s).,;:!?])/g, "$1$2")
    .replace(/\\([\\`*_{}\[\]()#+.!>-])/g, "$1")
    .replace(/<[^>]+>/g, "")
    .replace(/[ \t]+$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
