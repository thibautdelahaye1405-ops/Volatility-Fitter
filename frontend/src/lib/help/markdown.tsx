// Tiny Markdown renderer for the Help Center (HELP CENTER ARC, H4) — enough
// of CommonMark for the built-in guides and the technical notes' Markdown
// editions, with NO dependency (the bundle stays lean, offline mode keeps the
// guides). Block level: ATX headings, paragraphs, bullet / numbered lists
// (one nesting level), fenced code, blockquotes, pipe tables, `---` rules.
// Inline: **bold**, *italic*, `code`, links (help: / cmd: schemes become
// in-app navigation and action buttons through `onLink`), $math$ left
// verbatim in mono. Everything is escaped by React — no innerHTML.
import { Fragment } from "react";
import type { ReactNode } from "react";

export interface MarkdownHandlers {
  /** A `help:` or `cmd:` link (raw target); return true when handled. */
  onLink?: (target: string) => boolean;
}

type Block =
  | { t: "h"; level: number; text: string }
  | { t: "p"; text: string }
  | { t: "ul" | "ol"; items: string[][] }
  | { t: "code"; lang: string; text: string }
  | { t: "quote"; text: string }
  | { t: "table"; header: string[]; rows: string[][] }
  | { t: "hr" };

/** Split Markdown source into blocks (line-oriented, tolerant). */
export function parseBlocks(src: string): Block[] {
  const lines = src.replace(/\r\n?/g, "\n").split("\n");
  const out: Block[] = [];
  let i = 0;
  const para: string[] = [];
  const flush = () => {
    if (para.length) { out.push({ t: "p", text: para.join(" ").trim() }); para.length = 0; }
  };
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*$/.test(line)) { flush(); i++; continue; }
    if (/^```/.test(line)) {
      flush();
      const lang = line.slice(3).trim();
      const buf: string[] = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++;
      out.push({ t: "code", lang, text: buf.join("\n") });
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) { flush(); out.push({ t: "h", level: h[1].length, text: h[2].replace(/\s#+$/, "") }); i++; continue; }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { flush(); out.push({ t: "hr" }); i++; continue; }
    if (/^\s*>/.test(line)) {
      flush();
      const buf: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
      out.push({ t: "quote", text: buf.join(" ") });
      continue;
    }
    if (/^\s*\|/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      flush();
      const cells = (s: string) => s.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
      const header = cells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(cells(lines[i++]));
      out.push({ t: "table", header, rows });
      continue;
    }
    const li = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(line);
    if (li) {
      flush();
      const ordered = /\d/.test(li[2]);
      const items: string[][] = [];
      while (i < lines.length) {
        const m = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(lines[i]);
        if (m) {
          if (m[1].length >= 2 && items.length) items[items.length - 1].push("  " + m[3]);
          else if (/\d/.test(m[2]) !== ordered) break; // a list of the other kind starts
          else items.push([m[3]]);
          i++;
        } else if (/^\s{2,}\S/.test(lines[i]) && items.length) {
          items[items.length - 1][items[items.length - 1].length - 1] += " " + lines[i].trim();
          i++;
        } else break;
      }
      out.push({ t: ordered ? "ol" : "ul", items });
      continue;
    }
    para.push(line.trim());
    i++;
  }
  flush();
  return out;
}

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\$[^$]+\$|\[[^\]]+\]\([^)]+\)|\*[^*\s][^*]*\*)/g;

/** Render inline Markdown into React nodes. */
export function renderInline(text: string, h?: MarkdownHandlers, keyBase = ""): ReactNode[] {
  const parts = text.split(INLINE);
  return parts.map((part, idx) => {
    const key = `${keyBase}${idx}`;
    if (!part) return null;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={key} className="font-semibold text-slate-100">{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={key} className="rounded bg-surface-800 px-1 py-px font-mono text-[11px] text-accent-300">{part.slice(1, -1)}</code>;
    if (part.startsWith("$") && part.endsWith("$")) return <code key={key} className="font-mono text-[11px] text-slate-200">{part.slice(1, -1)}</code>;
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) return <em key={key}>{part.slice(1, -1)}</em>;
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (link) {
      const [, label, target] = link;
      const internal = target.startsWith("help:") || target.startsWith("cmd:");
      if (internal) {
        const isCmd = target.startsWith("cmd:");
        return (
          <button
            key={key}
            type="button"
            onClick={() => h?.onLink?.(target)}
            className={isCmd
              ? "inline-flex items-center rounded border border-accent-600/50 bg-accent-600/10 px-1.5 py-px text-[11px] font-medium text-accent-300 hover:bg-accent-600/20"
              : "text-accent-400 underline decoration-accent-600/50 underline-offset-2 hover:text-accent-300"}
          >
            {isCmd ? `▶ ${label}` : label}
          </button>
        );
      }
      return <a key={key} href={target} target="_blank" rel="noopener noreferrer" className="text-accent-400 underline underline-offset-2 hover:text-accent-300">{label}</a>;
    }
    return <Fragment key={key}>{part}</Fragment>;
  });
}

const H_CLASS: Record<number, string> = {
  1: "mt-1 text-lg font-semibold text-slate-100",
  2: "mt-5 text-sm font-semibold uppercase tracking-wider text-slate-300",
  3: "mt-4 text-[13px] font-semibold text-slate-200",
  4: "mt-3 text-xs font-semibold text-slate-300",
  5: "mt-2 text-xs font-semibold text-slate-400",
  6: "mt-2 text-[11px] font-semibold text-slate-400",
};

/** Slug used for heading anchors (scroll targets inside a page). */
export function headingSlug(text: string): string {
  return text.toLowerCase().replace(/[`*_$]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export function Markdown({ source, handlers, className }: { source: string; handlers?: MarkdownHandlers; className?: string }) {
  const blocks = parseBlocks(source);
  return (
    <div className={["help-md text-xs leading-relaxed text-slate-300", className ?? ""].join(" ")}>
      {blocks.map((b, i) => {
        switch (b.t) {
          case "h": {
            const Tag = `h${Math.min(6, b.level)}` as "h1";
            return <Tag key={i} id={headingSlug(b.text)} className={H_CLASS[Math.min(6, b.level)]}>{renderInline(b.text, handlers, `h${i}-`)}</Tag>;
          }
          case "p":
            return <p key={i} className="mt-2">{renderInline(b.text, handlers, `p${i}-`)}</p>;
          case "ul":
          case "ol": {
            const Tag = b.t;
            return (
              <Tag key={i} className={["mt-2 space-y-1 pl-5", b.t === "ul" ? "list-disc" : "list-decimal"].join(" ")}>
                {b.items.map((it, j) => (
                  <li key={j}>
                    {renderInline(it[0], handlers, `l${i}-${j}-`)}
                    {it.length > 1 && (
                      <ul className="mt-1 list-[circle] space-y-0.5 pl-5">
                        {it.slice(1).map((sub, k) => <li key={k}>{renderInline(sub.trim(), handlers, `l${i}-${j}-${k}-`)}</li>)}
                      </ul>
                    )}
                  </li>
                ))}
              </Tag>
            );
          }
          case "code":
            return (
              <pre key={i} className="mt-2 overflow-x-auto rounded-md border border-slate-800 bg-surface-950 p-3 font-mono text-[11px] text-slate-200">
                <code>{b.text}</code>
              </pre>
            );
          case "quote":
            return <blockquote key={i} className="mt-2 border-l-2 border-accent-600/60 pl-3 text-slate-400">{renderInline(b.text, handlers, `q${i}-`)}</blockquote>;
          case "table":
            return (
              <div key={i} className="mt-2 overflow-x-auto">
                <table className="w-full border-collapse text-[11px]">
                  <thead>
                    <tr>{b.header.map((c, j) => <th key={j} className="border-b border-slate-700 px-2 py-1 text-left font-semibold text-slate-200">{renderInline(c, handlers, `th${i}-${j}-`)}</th>)}</tr>
                  </thead>
                  <tbody>
                    {b.rows.map((r, j) => (
                      <tr key={j} className="odd:bg-surface-800/30">
                        {r.map((c, k) => <td key={k} className="border-b border-slate-800/60 px-2 py-1 align-top">{renderInline(c, handlers, `td${i}-${j}-${k}-`)}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          case "hr":
            return <hr key={i} className="my-4 border-slate-800" />;
        }
      })}
    </div>
  );
}
