package data

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// KBItem represents a structured item in the user's Knowledge Base.
type KBItem struct {
	ID         string   `json:"id"`
	Title      string   `json:"title"`
	Category   string   `json:"category"` // "Tools", "Metrics", "Facts", "Projects", "Claims"
	Content    string   `json:"content"`
	Tags       []string `json:"tags"`
	Confidence string   `json:"confidence"`
	Source     string   `json:"source"`
}

type toolsJSONFile struct {
	Tools []struct {
		ID            string   `json:"id"`
		Name          string   `json:"name"`
		Category      string   `json:"category"`
		Confidence    string   `json:"confidence"`
		EvidenceCount int      `json:"evidence_count"`
		UseNotes      string   `json:"use_notes"`
		References    []string `json:"tr_references"`
	} `json:"tools"`
}

type metricsJSONFile struct {
	Metrics []struct {
		ID         string `json:"id"`
		Label      string `json:"label"`
		Value      string `json:"value"`
		Volume     string `json:"volume"`
		Category   string `json:"category"`
		Confidence string `json:"confidence"`
		Context    string `json:"context"`
		Source     string `json:"source"`
		Caveat     string `json:"caveat"`
	} `json:"metrics"`
}

type factsJSONFile struct {
	Facts []struct {
		ID         string `json:"id"`
		Statement  string `json:"statement"`
		Category   string `json:"category"`
		Confidence string `json:"confidence"`
		Context    string `json:"context"`
		Source     string `json:"source"`
	} `json:"facts"`
}

type projectsJSONFile struct {
	Projects []struct {
		ID          string   `json:"id"`
		Name        string   `json:"name"`
		Role        string   `json:"role"`
		Impact      string   `json:"impact"`
		Stack       []string `json:"stack"`
		Description string   `json:"description"`
		Source      string   `json:"source"`
	} `json:"projects"`
}

// LoadKBItems loads and normalizes all available knowledge base assets.
func LoadKBItems(kbDir string) []KBItem {
	var items []KBItem

	// 1. Load verified tools
	toolsPath := filepath.Join(kbDir, "verified_tools.json")
	if data, err := os.ReadFile(toolsPath); err == nil {
		var tf toolsJSONFile
		if err := json.Unmarshal(data, &tf); err == nil {
			for _, t := range tf.Tools {
				var content strings.Builder
				content.WriteString(fmt.Sprintf("### %s\n\n", t.Name))
				content.WriteString(fmt.Sprintf("- **Category:** %s\n", t.Category))
				content.WriteString(fmt.Sprintf("- **Confidence:** %s\n", t.Confidence))
				if t.EvidenceCount > 0 {
					content.WriteString(fmt.Sprintf("- **Evidence Count:** %d\n", t.EvidenceCount))
				}
				if t.UseNotes != "" {
					content.WriteString(fmt.Sprintf("\n**Usage Notes:**\n%s\n", t.UseNotes))
				}
				if len(t.References) > 0 {
					content.WriteString(fmt.Sprintf("\n**References:** %s\n", strings.Join(t.References, ", ")))
				}

				items = append(items, KBItem{
					ID:         t.ID,
					Title:      t.Name,
					Category:   "Tools",
					Content:    content.String(),
					Tags:       []string{t.Category},
					Confidence: t.Confidence,
					Source:     "verified_tools.json",
				})
			}
		}
	}

	// 2. Load verified metrics
	metricsPath := filepath.Join(kbDir, "verified_metrics.json")
	if data, err := os.ReadFile(metricsPath); err == nil {
		var mf metricsJSONFile
		if err := json.Unmarshal(data, &mf); err == nil {
			for _, m := range mf.Metrics {
				var content strings.Builder
				content.WriteString(fmt.Sprintf("### %s\n\n", m.Label))
				content.WriteString(fmt.Sprintf("**Value:** %s\n\n", m.Value))
				if m.Volume != "" {
					content.WriteString(fmt.Sprintf("- **Volume:** %s\n", m.Volume))
				}
				if m.Category != "" {
					content.WriteString(fmt.Sprintf("- **Category:** %s\n", m.Category))
				}
				if m.Confidence != "" {
					content.WriteString(fmt.Sprintf("- **Confidence:** %s\n", m.Confidence))
				}
				if m.Source != "" {
					content.WriteString(fmt.Sprintf("- **Source:** %s\n", m.Source))
				}
				if m.Context != "" {
					content.WriteString(fmt.Sprintf("\n**Context:**\n%s\n", m.Context))
				}
				if m.Caveat != "" {
					content.WriteString(fmt.Sprintf("\n> **Caveat:** %s\n", m.Caveat))
				}

				items = append(items, KBItem{
					ID:         m.ID,
					Title:      m.Label,
					Category:   "Metrics",
					Content:    content.String(),
					Tags:       []string{m.Category},
					Confidence: m.Confidence,
					Source:     m.Source,
				})
			}
		}
	}

	// 3. Load verified facts
	factsPath := filepath.Join(kbDir, "verified_facts.json")
	if data, err := os.ReadFile(factsPath); err == nil {
		var ff factsJSONFile
		if err := json.Unmarshal(data, &ff); err == nil {
			for _, f := range ff.Facts {
				var content strings.Builder
				content.WriteString(fmt.Sprintf("### %s\n\n", f.Statement))
				if f.Category != "" {
					content.WriteString(fmt.Sprintf("- **Category:** %s\n", f.Category))
				}
				if f.Confidence != "" {
					content.WriteString(fmt.Sprintf("- **Confidence:** %s\n", f.Confidence))
				}
				if f.Source != "" {
					content.WriteString(fmt.Sprintf("- **Source:** %s\n", f.Source))
				}
				if f.Context != "" {
					content.WriteString(fmt.Sprintf("\n**Context:**\n%s\n", f.Context))
				}

				items = append(items, KBItem{
					ID:         f.ID,
					Title:      f.Statement,
					Category:   "Facts",
					Content:    content.String(),
					Tags:       []string{f.Category},
					Confidence: f.Confidence,
					Source:     f.Source,
				})
			}
		}
	}

	// 4. Load verified projects
	projectsPath := filepath.Join(kbDir, "verified_projects.json")
	if data, err := os.ReadFile(projectsPath); err == nil {
		var pf projectsJSONFile
		if err := json.Unmarshal(data, &pf); err == nil {
			for _, p := range pf.Projects {
				var content strings.Builder
				content.WriteString(fmt.Sprintf("### %s\n\n", p.Name))
				if p.Role != "" {
					content.WriteString(fmt.Sprintf("- **Role:** %s\n", p.Role))
				}
				if len(p.Stack) > 0 {
					content.WriteString(fmt.Sprintf("- **Tech Stack:** %s\n", strings.Join(p.Stack, ", ")))
				}
				if p.Impact != "" {
					content.WriteString(fmt.Sprintf("\n**Impact:**\n%s\n", p.Impact))
				}
				if p.Description != "" {
					content.WriteString(fmt.Sprintf("\n**Description:**\n%s\n", p.Description))
				}

				items = append(items, KBItem{
					ID:       p.ID,
					Title:    p.Name,
					Category: "Projects",
					Content:  content.String(),
					Tags:     p.Stack,
					Source:   p.Source,
				})
			}
		}
	}

	return items
}
