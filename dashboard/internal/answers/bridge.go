package answers

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"

	tea "charm.land/bubbletea/v2"
)

type TurnRequest struct {
	Job       string `json:"job"`
	Question  string `json:"question"`
	CharLimit int    `json:"char_limit,omitempty"`
	History   any    `json:"history,omitempty"`
	Action    string `json:"action,omitempty"`
}

type StatusMsg struct{ Message string }
type AnswerMsg struct {
	Answer    string
	Kind      string
	CharLimit int
	Warnings  []string
	Action    string
}
type ErrorMsg struct{ Err error }

func Turn(ctx context.Context, pythonPath, projectRoot string, req TurnRequest) tea.Cmd {
	return func() tea.Msg {
		payload, err := json.Marshal(req)
		if err != nil {
			return ErrorMsg{Err: err}
		}
		cmd := exec.CommandContext(ctx, pythonPath,
			projectRoot+"/scripts/application_answers.py", "turn",
		)
		cmd.Dir = projectRoot
		cmd.Stdin = strings.NewReader(string(payload))
		stdout, err := cmd.StdoutPipe()
		if err != nil {
			return ErrorMsg{Err: err}
		}
		var stderr strings.Builder
		cmd.Stderr = &stderr
		if err := cmd.Start(); err != nil {
			return ErrorMsg{Err: err}
		}
		var answer *AnswerMsg
		scanner := bufio.NewScanner(stdout)
		for scanner.Scan() {
			var event struct {
				Type      string   `json:"type"`
				Message   string   `json:"message"`
				Answer    string   `json:"text"`
				Kind      string   `json:"kind"`
				CharLimit int      `json:"char_limit"`
				Warnings  []string `json:"warnings"`
				Error     string   `json:"error"`
			}
			if json.Unmarshal(scanner.Bytes(), &event) != nil {
				continue
			}
			switch event.Type {
			case "status":
				// Status messages are intentionally consumed here. The
				// screen displays the stable "Thinking…" state while the
				// subprocess is active; answer/error events are the public
				// result of the command.
			case "answer":
				answer = &AnswerMsg{Answer: event.Answer, Kind: event.Kind, CharLimit: event.CharLimit, Warnings: event.Warnings, Action: req.Action}
			case "error":
				return ErrorMsg{Err: fmt.Errorf("%s", event.Error)}
			}
		}
		if scanErr := scanner.Err(); scanErr != nil {
			return ErrorMsg{Err: scanErr}
		}
		if err := cmd.Wait(); err != nil {
			detail := strings.TrimSpace(stderr.String())
			if detail == "" {
				detail = err.Error()
			}
			return ErrorMsg{Err: fmt.Errorf("%s", detail)}
		}
		if answer == nil {
			return ErrorMsg{Err: fmt.Errorf("answer engine returned no answer")}
		}
		return *answer
	}
}

func Load(ctx context.Context, pythonPath, projectRoot, job string) tea.Cmd {
	return func() tea.Msg {
		cmd := exec.CommandContext(ctx, pythonPath, projectRoot+"/scripts/application_answers.py", "load", "--job", job)
		cmd.Dir = projectRoot
		out, err := cmd.Output()
		if err != nil {
			return ErrorMsg{Err: err}
		}
		return out
	}
}

func EncodeHistory(items []map[string]any) string {
	data, _ := json.Marshal(items)
	return string(data)
}
