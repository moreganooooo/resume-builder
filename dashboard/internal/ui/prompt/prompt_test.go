package prompt

import (
	"encoding/json"
	"testing"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func TestSpecUnmarshal_Confirm(t *testing.T) {
	raw := `{"type":"confirm","message":"Ready?","default":true}`
	var spec Spec
	if err := json.Unmarshal([]byte(raw), &spec); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if spec.Type != "confirm" {
		t.Errorf("Type = %q, want %q", spec.Type, "confirm")
	}
	if spec.Message != "Ready?" {
		t.Errorf("Message = %q, want %q", spec.Message, "Ready?")
	}
	if !spec.Default {
		t.Errorf("Default = false, want true")
	}
}

func TestSpecUnmarshal_SelectWithOptions(t *testing.T) {
	raw := `{"type":"select","message":"Pick one","options":[{"label":"A","value":"a"},{"label":"B","value":"b"}],"default_value":"b"}`
	var spec Spec
	if err := json.Unmarshal([]byte(raw), &spec); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if len(spec.Options) != 2 {
		t.Fatalf("len(Options) = %d, want 2", len(spec.Options))
	}
	if spec.Options[0].Label != "A" || spec.Options[0].Value != "a" {
		t.Errorf("Options[0] = %+v, want {A a}", spec.Options[0])
	}
	if spec.DefaultValue != "b" {
		t.Errorf("DefaultValue = %q, want %q", spec.DefaultValue, "b")
	}
}

func TestSpecUnmarshal_TextWithDefaultValue(t *testing.T) {
	raw := `{"type":"text","message":"Archive postings older than how many days?","default_value":"30"}`
	var spec Spec
	if err := json.Unmarshal([]byte(raw), &spec); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if spec.Type != "text" {
		t.Errorf("Type = %q, want %q", spec.Type, "text")
	}
	if spec.DefaultValue != "30" {
		t.Errorf("DefaultValue = %q, want %q", spec.DefaultValue, "30")
	}
}

func TestResultMarshal_Confirm(t *testing.T) {
	answer := true
	result := Result{Confirmed: &answer}
	out, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}
	if string(out) != `{"confirmed":true}` {
		t.Errorf("Marshal = %s, want %s", out, `{"confirmed":true}`)
	}
}

func TestResultMarshal_Select(t *testing.T) {
	result := Result{Value: "b"}
	out, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}
	if string(out) != `{"value":"b"}` {
		t.Errorf("Marshal = %s, want %s", out, `{"value":"b"}`)
	}
}

func TestResultMarshal_Checkbox(t *testing.T) {
	result := Result{Values: []string{"bullets", "profile"}}
	out, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}
	if string(out) != `{"values":["bullets","profile"]}` {
		t.Errorf("Marshal = %s, want %s", out, `{"values":["bullets","profile"]}`)
	}
}

func TestRun_UnknownTypeErrors(t *testing.T) {
	_, err := Run(theme.Theme{}, Spec{Type: "bogus"})
	if err == nil {
		t.Fatal("expected an error for an unknown prompt type, got nil")
	}
}
