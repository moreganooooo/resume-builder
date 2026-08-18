package data

import (
	"testing"
)

func TestNormalizeUnicodeSearch(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{
			name:     "empty string",
			input:    "",
			expected: "",
		},
		{
			name:     "plain ascii",
			input:    "Hello World",
			expected: "hello world",
		},
		{
			name:     "zero-width spaces and BOM",
			input:    "Acme\u200B\uFEFF Corp\u200C\u200D",
			expected: "acme corp",
		},
		{
			name:     "non-breaking spaces",
			input:    "Staff\u00A0Engineer\u202FLead",
			expected: "staff engineer lead",
		},
		{
			name:     "curly quotes and apostrophes",
			input:    "“L’Oreal” and ‘Acme’",
			expected: "\"l'oreal\" and 'acme'",
		},
		{
			name:     "em and en dashes",
			input:    "Frontend—Backend–Fullstack",
			expected: "frontend-backend-fullstack",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := NormalizeUnicodeSearch(tc.input)
			if got != tc.expected {
				t.Errorf("NormalizeUnicodeSearch(%q) = %q, expected %q", tc.input, got, tc.expected)
			}
		})
	}
}
