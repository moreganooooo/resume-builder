package data

import (
	"strings"
	"unicode"
)

// NormalizeUnicodeSearch sanitizes and normalizes a search query string.
// It removes zero-width characters (BOM, zero-width space/joiners),
// replaces non-breaking spaces with standard spaces, normalizes curly/smart
// quotes to ASCII equivalents, and converts to lowercase for case-insensitive
// cross-platform search and clipboard pasting.
func NormalizeUnicodeSearch(s string) string {
	if s == "" {
		return ""
	}

	var sb strings.Builder
	sb.Grow(len(s))

	for _, r := range s {
		switch r {
		case '\u200B', '\u200C', '\u200D', '\uFEFF':
			// Skip zero-width chars
			continue
		case '\u00A0', '\u202F', '\u2007':
			// Non-breaking spaces -> standard space
			sb.WriteRune(' ')
		case '\u2018', '\u2019', '\u201B', '`', '´':
			// Smart single quotes / grave / acute -> ASCII single quote
			sb.WriteRune('\'')
		case '\u201C', '\u201D', '\u201F', '«', '»':
			// Smart double quotes / guillemets -> ASCII double quote
			sb.WriteRune('"')
		case '\u2013', '\u2014', '\u2015':
			// En-dash, Em-dash, Horizontal bar -> ASCII hyphen
			sb.WriteRune('-')
		case 'é', 'è', 'ê', 'ë', 'ē', 'ė', 'ę', 'É', 'È', 'Ê', 'Ë', 'Ē', 'Ė', 'Ę':
			sb.WriteRune('e')
		case 'á', 'à', 'â', 'ä', 'ã', 'å', 'ā', 'Á', 'À', 'Â', 'Ä', 'Ã', 'Å', 'Ā':
			sb.WriteRune('a')
		case 'í', 'ì', 'î', 'ï', 'ī', 'į', 'Í', 'Ì', 'Î', 'Ï', 'Ī', 'Į':
			sb.WriteRune('i')
		case 'ó', 'ò', 'ô', 'ö', 'õ', 'ø', 'ō', 'Ó', 'Ò', 'Ô', 'Ö', 'Õ', 'Ø', 'Ō':
			sb.WriteRune('o')
		case 'ú', 'ù', 'û', 'ü', 'ū', 'Ú', 'Ù', 'Û', 'Ü', 'Ū':
			sb.WriteRune('u')
		case 'ñ', 'ń', 'Ñ', 'Ń':
			sb.WriteRune('n')
		case 'ç', 'ć', 'č', 'Ç', 'Ć', 'Č':
			sb.WriteRune('c')
		default:
			sb.WriteRune(unicode.ToLower(r))
		}
	}

	return strings.TrimSpace(sb.String())
}
