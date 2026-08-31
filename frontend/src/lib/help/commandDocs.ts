// Command reference (HELP CENTER ARC, H2) — the documentation of every registry
// command in lib/commands.ts plus the DYNAMIC prefixes, assembled from three
// parts kept under the 400-line policy:
//   commandDocs_file.ts   File · Export · Universe · Fetch · Calibrate · Priors
//   commandDocs_shell.ts  Lens · Layout · Tabs · View
//   commandDocs_help.ts   Help / dialogs · the Help Center rows · dynamic prefixes
// The completeness lock (commandDocs.test.ts) reads COMMAND_DOCS: every
// COMMANDS id has a doc, every doc names a registry id or a DYNAMIC prefix.
import type { CommandDoc } from "./types";
import { COMMAND_DOCS_FILE } from "./commandDocs_file";
import { COMMAND_DOCS_SHELL } from "./commandDocs_shell";
import { COMMAND_DOCS_HELP } from "./commandDocs_help";

export const COMMAND_DOCS: CommandDoc[] = [
  ...COMMAND_DOCS_FILE,
  ...COMMAND_DOCS_SHELL,
  ...COMMAND_DOCS_HELP,
];

const BY_ID: Record<string, CommandDoc> = Object.fromEntries(COMMAND_DOCS.map((d) => [d.id, d]));

/** Doc lookup by exact id, or by the DYNAMIC prefix a runtime id starts with
 *  ("universe.load:us-tech" → the "universe.load:" doc). Undefined when unknown. */
export function commandDoc(id: string): CommandDoc | undefined {
  const exact = BY_ID[id];
  if (exact) return exact;
  const prefix = COMMAND_DOCS.find((d) => d.id.endsWith(":") && id.startsWith(d.id));
  return prefix;
}
