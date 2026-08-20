/** Clean AI-generated text for display: strip markdown headers, LaTeX, and code fences. */

const LATEX_PATTERNS: Array<{ re: RegExp; replace: string | ((m: string, g1?: string, g2?: string) => string) }> = [
  { re: /\$\$([\s\S]*?)\$\$/g, replace: "" }, // display math $$...$$
  { re: /\$([^$]+)\$/g, replace: "$1" }, // inline math $...$
  { re: /\\frac\{([^}]+)\}\{([^}]+)\}/g, replace: (_m: string, g1?: string, g2?: string) => `${g1 || ""}/${g2 || ""}` },
  { re: /\\sqrt\{([^}]+)\}/g, replace: (_m: string, g1?: string) => `√${g1 || ""}` },
  { re: /\\times/g, replace: "×" },
  { re: /\\cdot/g, replace: "·" },
  { re: /\\pm/g, replace: "±" },
  { re: /\\leq/g, replace: "≤" },
  { re: /\\geq/g, replace: "≥" },
  { re: /\\neq/g, replace: "≠" },
  { re: /\\circ/g, replace: "°" },
  { re: /\\angle/g, replace: "∠" },
  { re: /\\triangle/g, replace: "△" },
  { re: /\\pi/g, replace: "π" },
  { re: /\\theta/g, replace: "θ" },
  { re: /\\alpha/g, replace: "α" },
  { re: /\\beta/g, replace: "β" },
  { re: /\\gamma/g, replace: "γ" },
  { re: /\\Delta/g, replace: "Δ" },
  { re: /\\Sigma/g, replace: "Σ" },
  { re: /\\begin\{[^}]+\}/g, replace: "" },
  { re: /\\end\{[^}]+\}/g, replace: "" },
  { re: /\\\\/g, replace: "" }, // double backslash
  { re: /\\\(/g, replace: "" }, // \(
  { re: /\\\)/g, replace: "" }, // \)
  { re: /\\\[/g, replace: "" }, // \[
  { re: /\\\]/g, replace: "" }, // \]
  { re: /\^\{([^}]+)\}/g, replace: (_m: string, g1?: string) => g1 ? [...g1].map((c: string) => SUPERSCRIPT_MAP[c] || c).join("") : "" },
  { re: /_\{([^}]+)\}/g, replace: (_m: string, g1?: string) => g1 ? [...g1].map((c: string) => SUBSCRIPT_MAP[c] || c).join("") : "" },
];

const SUPERSCRIPT_MAP: Record<string, string> = {
  "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
  "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
  "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
};

const SUBSCRIPT_MAP: Record<string, string> = {
  "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
  "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
  "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
  "a": "ₐ", "e": "ₑ", "o": "ₒ", "x": "ₓ",
};

function convertSuperscripts(text: string): string {
  return text.replace(/\^{([^}]+)}/g, (_, inner) =>
    [...inner].map(c => SUPERSCRIPT_MAP[c] || c).join("")
  );
}

function convertSubscripts(text: string): string {
  return text.replace(/_\{([^}]+)\}/g, (_, inner) =>
    [...inner].map(c => SUBSCRIPT_MAP[c] || c).join("")
  );
}

/** Strip markdown headers (###, ##, #) and leading hash+space */
function stripMarkdownHeaders(text: string): string {
  return text.replace(/^#{1,6}\s+/gm, "");
}

/** Strip markdown bold/italic markers */
function stripMarkdownFormatting(text: string): string {
  return text
    .replace(/\*\*\*(.+?)\*\*\*/g, "$1") // ***bold italic***
    .replace(/\*\*(.+?)\*\*/g, "$1") // **bold**
    .replace(/\*(.+?)\*/g, "$1") // *italic*
    .replace(/__(.+?)__/g, "$1") // __bold__
    .replace(/_(.+?)_/g, "$1"); // _italic_
}

/** Strip markdown code fences */
function stripCodeFences(text: string): string {
  return text.replace(/```[\s\S]*?```/g, "").replace(/`([^`]+)`/g, "$1");
}

/** Strip LaTeX from text, converting to plain Unicode where possible */
function stripLatex(text: string): string {
  let result = text;
  // Convert superscripts/subscripts before removing braces
  result = convertSuperscripts(result);
  result = convertSubscripts(result);
  // Replace known LaTeX commands
  for (const { re, replace } of LATEX_PATTERNS) {
    if (typeof replace === "function") {
      result = result.replace(re, replace);
    } else {
      result = result.replace(re, replace);
    }
  }
  // Clean up leftover backslashes
  result = result.replace(/\\/g, "");
  // Clean up leftover braces
  result = result.replace(/[{}]/g, "");
  return result;
}

/** Full cleanup: strip headers, LaTeX, markdown formatting */
export function cleanAiText(text: string | null | undefined): string {
  if (!text) return "";
  let result = text;
  result = stripMarkdownHeaders(result);
  result = stripCodeFences(result);
  result = stripLatex(result);
  result = stripMarkdownFormatting(result);
  // Collapse excessive whitespace
  result = result.replace(/\n{3,}/g, "\n\n").trim();
  return result;
}
