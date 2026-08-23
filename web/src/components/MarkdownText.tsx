import { Fragment, ReactNode } from "react";

// LLM answers come back as Markdown (bullet lists, **bold**) - Streamlit's
// st.write() rendered that implicitly, so this replaces that behavior for
// the small subset of Markdown chat answers actually use: paragraphs,
// "-"/"*" bullet lists, and **bold** spans. Not a general Markdown parser.
export default function MarkdownText({ text }: { text: string }) {
  const blocks = text
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);

  return (
    <>
      {blocks.map((block, index) => {
        const lines = block
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean);
        const isList = lines.length > 0 && lines.every((line) => /^[-*]\s+/.test(line));

        if (isList) {
          return (
            <ul key={index}>
              {lines.map((line, lineIndex) => (
                <li key={lineIndex}>{renderInline(line.replace(/^[-*]\s+/, ""))}</li>
              ))}
            </ul>
          );
        }

        return (
          <p key={index}>
            {lines.map((line, lineIndex) => (
              <Fragment key={lineIndex}>
                {lineIndex > 0 && <br />}
                {renderInline(line)}
              </Fragment>
            ))}
          </p>
        );
      })}
    </>
  );
}

function renderInline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={index}>{part.slice(2, -2)}</strong> : part,
  );
}
