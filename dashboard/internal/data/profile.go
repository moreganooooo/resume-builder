package data

import (
	"bufio"
	"os"
	"path/filepath"
	"strings"
)

// ProfileInfo contains metadata for a user profile.
type ProfileInfo struct {
	Name     string
	Path     string
	Role     string
	IsActive bool
}

// DiscoverProfiles scans the profiles directory and returns all available profiles.
func DiscoverProfiles(projectRoot string, activeProfile string) []ProfileInfo {
	if activeProfile == "" {
		activeProfile = "morgan"
	}

	profilesDir := filepath.Join(projectRoot, "profiles")
	entries, err := os.ReadDir(profilesDir)
	if err != nil {
		return []ProfileInfo{
			{
				Name:     activeProfile,
				Path:     filepath.Join(profilesDir, activeProfile),
				Role:     "Default Profile",
				IsActive: true,
			},
		}
	}

	var results []ProfileInfo
	for _, entry := range entries {
		if !entry.IsDir() || strings.HasPrefix(entry.Name(), ".") {
			continue
		}

		name := entry.Name()
		profPath := filepath.Join(profilesDir, name)
		role := parseTargetRole(profPath)
		if role == "" {
			role = name
		}

		results = append(results, ProfileInfo{
			Name:     name,
			Path:     profPath,
			Role:     role,
			IsActive: name == activeProfile,
		})
	}

	if len(results) == 0 {
		results = append(results, ProfileInfo{
			Name:     activeProfile,
			Path:     filepath.Join(profilesDir, activeProfile),
			Role:     "Default Profile",
			IsActive: true,
		})
	}

	return results
}

// LoadActiveProfile returns information for the given active profile.
func LoadActiveProfile(projectRoot string, profileName string) ProfileInfo {
	if profileName == "" {
		profileName = "morgan"
	}

	profPath := filepath.Join(projectRoot, "profiles", profileName)
	role := parseTargetRole(profPath)
	if role == "" {
		role = profileName
	}

	return ProfileInfo{
		Name:     profileName,
		Path:     profPath,
		Role:     role,
		IsActive: true,
	}
}

func parseTargetRole(profileDir string) string {
	ymlPath := filepath.Join(profileDir, "profile.yml")
	f, err := os.Open(ymlPath)
	if err != nil {
		return ""
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if strings.HasPrefix(line, "target_role:") {
			val := strings.TrimPrefix(line, "target_role:")
			val = strings.Trim(strings.TrimSpace(val), "\"'")
			if val != "" {
				return val
			}
		}
		if strings.HasPrefix(line, "headline:") {
			val := strings.TrimPrefix(line, "headline:")
			val = strings.Trim(strings.TrimSpace(val), "\"'")
			if val != "" {
				return val
			}
		}
	}
	return ""
}
