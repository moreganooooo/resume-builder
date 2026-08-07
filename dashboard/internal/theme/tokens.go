package theme

import (
    "encoding/json"
    "os"
    "path/filepath"
)

type ColorMeta struct {
    Role        string `json:"role"`
    DisplayName string `json:"displayName"`
}

type DesignTokens struct {
    TUIBase   ColorMeta `json:"tui-base"`
    TUIBrand  ColorMeta `json:"tui-brand"`
    TUIAccent ColorMeta `json:"tui-accent"`
    PrintText ColorMeta `json:"print-text"`
}

var Tokens DesignTokens

func init() {
    // Find the project root containing .impeccable/design.json.
    cwd, err := os.Getwd()
    if err != nil {
        panic(err)
    }
    root := cwd
    for i := 0; i < 6; i++ {
        if _, err := os.Stat(filepath.Join(root, ".impeccable", "design.json")); err == nil {
            break
        }
        root = filepath.Dir(root)
    }
    designPath := filepath.Join(root, ".impeccable", "design.json")
    data, err := os.ReadFile(designPath)
    if err != nil {
        panic(err)
    }
    var raw struct {
        Extensions struct {
            ColorMeta map[string]ColorMeta `json:"colorMeta"`
        } `json:"extensions"`
    }
    if err := json.Unmarshal(data, &raw); err != nil {
        panic(err)
    }
    Tokens = DesignTokens{
        TUIBase:   raw.Extensions.ColorMeta["tui-base"],
        TUIBrand:  raw.Extensions.ColorMeta["tui-brand"],
        TUIAccent: raw.Extensions.ColorMeta["tui-accent"],
        PrintText: raw.Extensions.ColorMeta["print-text"],
    }
}

// Hex returns a deterministic hex colour for a role.
func (c ColorMeta) Hex() string {
    switch c.Role {
    case "primary":
        return "#4dabf7"
    case "secondary":
        return "#cba6f7"
    case "neutral":
        return "#313244"
    default:
        return "#bbbbbb"
    }
}

// Exported colour shortcuts used throughout the UI.
var (
    BaseColor   = Tokens.TUIBase.Hex()
    BrandColor  = Tokens.TUIBrand.Hex()
    AccentColor = Tokens.TUIAccent.Hex()
    PrintColor  = Tokens.PrintText.Hex()
)
