export interface CliBannerProps {
  /** Bold line under the wordmark. */
  tagline?: string;
  /** Live profile counts, rendered in Blue under the tagline. */
  lines?: string[];
}

/** The CLI launcher wordmark: the real ANSI Shadow rows on a Sky-to-Mauve diagonal gradient, in a double-ruled Sky panel. */
export declare function CliBanner(props: CliBannerProps): JSX.Element;
