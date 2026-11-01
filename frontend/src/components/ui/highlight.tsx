import { Fragment } from "react";

/** The query's words, longest first so "createStore" wins over "create" */
function words(query: string): string[] {
  return [...new Set(query.toLowerCase().match(/[\p{L}\p{N}_$]{2,}/gu) ?? [])].sort(
    (a, b) => b.length - a.length
  );
}

/**
 * Text with the query's words marked. Everything renders as text nodes, so code such as
 * `<script>` in a snippet shows as written and can't inject markup.
 */
export function Highlight({ text, query }: { text: string; query: string }) {
  const terms = words(query);
  if (!text || terms.length === 0) return <>{text}</>;
  const pattern = new RegExp(
    `(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "giu"
  );
  // split() with a capture group puts the matches at the odd indexes
  return (
    <>
      {text.split(pattern).map((part, i) =>
        i % 2 ? <mark key={i}>{part}</mark> : <Fragment key={i}>{part}</Fragment>
      )}
    </>
  );
}
