package data

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDiscoverProfiles(t *testing.T) {
	tempDir := t.TempDir()
	profilesDir := filepath.Join(tempDir, "profiles")
	_ = os.MkdirAll(filepath.Join(profilesDir, "morgan"), 0755)
	_ = os.MkdirAll(filepath.Join(profilesDir, "alex"), 0755)
	_ = os.MkdirAll(filepath.Join(profilesDir, ".hidden"), 0755)

	// Write mock profile.yml
	morganYml := `name: Morgan Escott
target_role: Staff Software Engineer
`
	_ = os.WriteFile(filepath.Join(profilesDir, "morgan", "profile.yml"), []byte(morganYml), 0644)

	profiles := DiscoverProfiles(tempDir, "morgan")
	if len(profiles) < 2 {
		t.Fatalf("expected at least 2 profiles, got %d", len(profiles))
	}

	var foundMorgan, foundAlex bool
	for _, p := range profiles {
		if p.Name == "morgan" {
			foundMorgan = true
			if !p.IsActive {
				t.Errorf("expected morgan to be active")
			}
			if p.Role != "Staff Software Engineer" && p.Role != "morgan" {
				t.Errorf("unexpected role for morgan: %s", p.Role)
			}
		}
		if p.Name == "alex" {
			foundAlex = true
			if p.IsActive {
				t.Errorf("alex should not be active")
			}
		}
		if p.Name == ".hidden" {
			t.Errorf("hidden directory should not be discovered as a profile")
		}
	}

	if !foundMorgan || !foundAlex {
		t.Errorf("failed to discover expected profiles: foundMorgan=%v, foundAlex=%v", foundMorgan, foundAlex)
	}
}

func TestLoadActiveProfile(t *testing.T) {
	tempDir := t.TempDir()
	profilesDir := filepath.Join(tempDir, "profiles", "default_user")
	_ = os.MkdirAll(profilesDir, 0755)

	profile := LoadActiveProfile(tempDir, "default_user")
	if profile.Name != "default_user" {
		t.Errorf("expected profile name 'default_user', got %s", profile.Name)
	}
	if !profile.IsActive {
		t.Errorf("expected active profile to have IsActive=true")
	}
}
