import type { CSSProperties } from "react";

/**
 * NetHack's 16-color terminal palette.
 * Index 7 (CLR_GRAY) is the default text color and renders unstyled.
 */
const NETHACK_COLORS: string[] = [
  "#636363", //  0 CLR_BLACK (dark gray — visible on dark bg)
  "#d03030", //  1 CLR_RED
  "#30c030", //  2 CLR_GREEN
  "#c0a030", //  3 CLR_BROWN
  "#4040e0", //  4 CLR_BLUE (brightened for dark bg)
  "#c030c0", //  5 CLR_MAGENTA
  "#30c0c0", //  6 CLR_CYAN
  "#c0c0c0", //  7 CLR_GRAY (default)
  "#808080", //  8 CLR_DARK_GRAY
  "#ff4040", //  9 CLR_BRIGHT_RED
  "#40ff40", // 10 CLR_BRIGHT_GREEN
  "#ffff40", // 11 CLR_YELLOW
  "#6060ff", // 12 CLR_BRIGHT_BLUE
  "#ff40ff", // 13 CLR_BRIGHT_MAGENTA
  "#40ffff", // 14 CLR_BRIGHT_CYAN
  "#ffffff", // 15 CLR_WHITE
];

/** Background color used for the game screen (matches dark theme). */
const BG_COLOR = "#0a0a0f";

/** Default foreground color index (CLR_GRAY). Rendered unstyled. */
const DEFAULT_COLOR = 7;

/**
 * Decode a base64-encoded color string to a flat Uint8Array.
 * Returns null on failure (invalid base64, wrong length, etc.).
 */
export function decodeColors(base64: string): Uint8Array | null {
  try {
    const binary = atob(base64);
    if (binary.length !== 1920) return null; // 24 rows * 80 cols
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  } catch {
    return null;
  }
}

/** A run of consecutive characters sharing the same color. */
export interface ColorRun {
  text: string;
  colorIndex: number;
}

/**
 * Group a line of text into runs of consecutive same-color characters.
 * `colorRow` is the 80-byte slice for this line from the decoded array.
 */
export function buildColorRuns(
  line: string,
  colorRow: Uint8Array,
): ColorRun[] {
  if (line.length === 0) return [];

  const runs: ColorRun[] = [];
  let currentColor = colorRow[0];
  let start = 0;

  for (let i = 1; i < line.length; i++) {
    if (colorRow[i] !== currentColor) {
      runs.push({ text: line.slice(start, i), colorIndex: currentColor });
      currentColor = colorRow[i];
      start = i;
    }
  }
  // Push the last run
  runs.push({ text: line.slice(start), colorIndex: currentColor });

  return runs;
}

/**
 * Get inline CSS style for a given NLE color index.
 * - Index 7 (CLR_GRAY) returns empty object (default text color).
 * - Index 0-15: foreground color only.
 * - Index 16-31: reverse video (bg = color, fg = dark bg).
 */
export function getColorStyle(colorIndex: number): CSSProperties {
  if (colorIndex === DEFAULT_COLOR) return {};

  // Reverse video: indices 16-31
  if (colorIndex >= 16 && colorIndex <= 31) {
    const baseIndex = colorIndex - 16;
    const bgHex = NETHACK_COLORS[baseIndex] ?? NETHACK_COLORS[DEFAULT_COLOR];
    return { backgroundColor: bgHex, color: BG_COLOR };
  }

  // Normal foreground color
  if (colorIndex >= 0 && colorIndex < NETHACK_COLORS.length) {
    return { color: NETHACK_COLORS[colorIndex] };
  }

  return {};
}
