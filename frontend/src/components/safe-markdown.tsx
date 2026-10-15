import type { ReactNode } from "react";

function inline(text: string): ReactNode[] {
  const pattern =
    /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*|\[[^\]\n]+\]\([^\s)]+\))/g;
  const output: ReactNode[] = [];
  let from = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index!;
    output.push(text.slice(from, index));
    const token = match[0];
    const key = index;
    if (token.startsWith("`"))
      output.push(<code key={key}>{token.slice(1, -1)}</code>);
    else if (token.startsWith("**"))
      output.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith("*"))
      output.push(<em key={key}>{token.slice(1, -1)}</em>);
    else {
      const split = token.indexOf("](");
      const href = token.slice(split + 2, -1);
      // No raw HTML, unsafe schemes, protocol-relative URLs, images or embeds.
      if (/^https?:\/\//i.test(href))
        output.push(
          <a key={key} href={href} target="_blank" rel="noopener noreferrer">
            {token.slice(1, split)}
          </a>,
        );
      else output.push(token);
    }
    from = index + token.length;
  }
  output.push(text.slice(from));
  return output;
}
export function SafeMarkdown({ body }: { body: string }) {
  const blocks = body.split(/(```[\s\S]*?```)/g);
  return (
    <div className="message-body" dir="auto">
      {blocks.map((block, index) =>
        block.startsWith("```") ? (
          <pre key={index}>
            <code>{block.slice(3, -3).replace(/^\w*\n/, "")}</code>
          </pre>
        ) : (
          <span key={index}>{inline(block)}</span>
        ),
      )}
    </div>
  );
}
