import React from "react";

const TAGS = {
  full_time: { label: "Full-time", color: "var(--tag-full-time)" },
  part_time: { label: "Part-time", color: "var(--tag-part-time)" },
  contract: { label: "Contract", color: "var(--tag-contract)" },
  contract_to_hire: { label: "Contract-to-hire", color: "var(--tag-contract-to-hire)" },
  temporary: { label: "Temporary", color: "var(--tag-temporary)" },
  internship: { label: "Internship", color: "var(--tag-internship)" },
};

// Bracketed bold label. full_time is Mauve, deliberately NOT Green — green
// is the score scale and shares the row.
export function EmploymentTag({ type }) {
  const t = TAGS[type] || { label: type, color: "var(--tui-subtext)" };
  return <span style={{ color: t.color, fontWeight: 700, fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>[{t.label}]</span>;
}
