package theme

// BaseColor/BrandColor/AccentColor/PrintColor used to be derived at
// runtime from .impeccable/design.json's extensions.colorMeta (role +
// displayName per token, e.g. tui-accent: {role: "secondary", displayName:
// "Vibrant Mauve"}), via a Role-keyed lookup table hardcoded in this
// package. That data was never going to be correct: colorMeta only ever
// carries a role classification, never a hex value, so the lookup table
// was guessing at colors the sidecar structurally cannot supply -- and
// because tui-base and print-text share the role "neutral" despite being
// two different DESIGN.md colors (#1e1e2e vs #000000), the guess couldn't
// even be internally consistent. tui-accent's "secondary" role resolved
// to "#cba6f7" (Catppuccin Mocha's stock mauve) instead of DESIGN.md's
// actual "#b39ddb" (Vibrant Mauve) for the same reason.
//
// DESIGN.md's own `colors:` block is the authoritative source; these are
// its tui-base/tui-brand/tui-accent/print-text values, hardcoded the same
// way every other palette in this package already is (see
// resumebuilder.go, catppuccin.go, catppuccin_latte.go) rather than
// re-derived from a file that was never able to carry them.
var (
	BaseColor   = "#1e1e2e" // tui-base / Deep Midnight
	BrandColor  = "#4dabf7" // tui-brand / Electric Sky
	AccentColor = "#b39ddb" // tui-accent / Vibrant Mauve
	PrintColor  = "#000000" // print-text / Print Black
)
