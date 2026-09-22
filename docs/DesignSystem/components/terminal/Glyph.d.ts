export declare const GLYPHS: Record<string, string>;
export interface GlyphProps {
  /** Icon name from the product's Unicode fallback table, or a literal character. */
  name: string;
  color?: string;
  size?: string | number;
  title?: string;
}
export declare function Glyph(props: GlyphProps): JSX.Element;
