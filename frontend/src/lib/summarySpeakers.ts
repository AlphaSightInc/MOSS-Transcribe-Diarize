import type { TranscriptItem } from "../api/types";
import type { SummaryDocument } from "./finalSummary";
import { UNATTRIBUTED_SPEAKER_LABEL } from "./speakerMap";
import { isSpacedWordCharacter } from "./text";
import { transcriptCardSpeakerLabel } from "./transcriptCards";

/** One name per speaker id. */
export type SpeakerNames = Readonly<Record<string, string>>;

/** The name each speaker carries in the transcript now; speech nobody is attributed to has none. */
export function transcriptSpeakerNames(
  items: readonly Pick<TranscriptItem, "speaker" | "speaker_entity_id" | "display_name" | "state">[]
): SpeakerNames {
  const names: Record<string, string> = {};
  for (const item of items) {
    const name = transcriptCardSpeakerLabel(item);
    if (name !== UNATTRIBUTED_SPEAKER_LABEL) names[item.speaker_entity_id] = name;
  }
  return names;
}

/**
 * A summary as it reads now. A summary is prose written once by a model that was given each
 * speaker under one name (`given`, saved with the summary); renaming a speaker never asks the
 * model again (issue #15). So every mention of a given name is shown as the name that speaker
 * carries in the transcript now (`current`). The stored document is not changed, which is why a
 * second rename, or a rename back, starts from the same text.
 *
 * Only names in `given` are looked for, so a default label the generator never used ("Speaker 1"
 * said aloud in a meeting whose first voice was already named) is ordinary text. A name is left
 * as written when the speaker is no longer in the transcript, or when two speakers were given
 * the same name and now differ (a mention could be either). A summary saved without `given`
 * (before round 5) is returned as stored: which names it was written with is unknown.
 */
export function renameSummarySpeakers(
  document: SummaryDocument, given: SpeakerNames | undefined, current: SpeakerNames
): SummaryDocument {
  if (!given) return document;
  const shown = new Map<string, Set<string>>();
  for (const [speaker, name] of Object.entries(given)) {
    if (!name) continue;
    if (!shown.has(name)) shown.set(name, new Set());
    shown.get(name)!.add(current[speaker] ?? name);
  }
  // Every given name takes part, longest first, so a name inside a longer one ("Ann" in
  // "Ann Lee", "Speaker 1" in "Speaker 10") belongs to the longer one, renamed or not.
  const names = [...shown].map(([name, now]) => [name, now.size === 1 ? [...now][0]! : name] as const)
    .sort((left, right) => right[0].length - left[0].length);
  if (names.every(([name, now]) => name === now)) return document;
  const rename = (text: string) => replaceNames(text, names);
  return {
    summary: rename(document.summary),
    topics: document.topics.map(topic => ({ title: rename(topic.title), description: rename(topic.description) })),
    details: document.details.map(detail => ({ ...detail, title: rename(detail.title), description: rename(detail.description) })),
    speaker_background: document.speaker_background.map(rename),
    data_references: document.data_references.map(item => ({ ...item, item: rename(item.item), context: rename(item.context) }))
  };
}

/** One pass over the text, so a new name is never renamed again (two speakers can swap names). */
function replaceNames(text: string, names: readonly (readonly [string, string])[]): string {
  let result = "";
  for (let at = 0; at < text.length;) {
    const hit = names.find(([name]) => text.startsWith(name, at) && isWholeName(text, at, name));
    result += hit ? hit[1] : text[at];
    at += hit ? hit[0].length : 1;
  }
  return result;
}

/**
 * A name must not continue a word: "Speaker 1" is not in "Speaker 10", nor "Al" in "Also".
 * Chinese puts no space between words, so a Chinese neighbour (or a Chinese name) needs no gap:
 * "Speaker 2介绍了…" and "张伟说…" are mentions.
 */
function isWholeName(text: string, at: number, name: string): boolean {
  const end = at + name.length;
  return !(isSpacedWordCharacter(name[0]) && isSpacedWordCharacter(text[at - 1])) &&
    !(isSpacedWordCharacter(name[name.length - 1]) && isSpacedWordCharacter(text[end]));
}
