export interface GlamourDocProps {
  /** Markdown source. Supported: `#`–`######` headings, `-`/`*` bullets, blank-line paragraphs, inline `**bold**`. */
  source: string;
  /** Left indent Glamour applies to the whole block. Default `"16.8px"` (two cells). */
  indent?: string;
}

/** Glamour-rendered markdown, as the Knowledge Base detail pane shows it. */
export declare function GlamourDoc(props: GlamourDocProps): JSX.Element;
