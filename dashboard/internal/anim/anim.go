// Package anim provides harmonica-powered spring physics curves and reduced-motion gating for TUI interfaces.
package anim

import (
	"os"
	"strings"

	"github.com/charmbracelet/harmonica"
)

// Curve represents spring physics parameters: frequency (speed/stiffness) and damping ratio.
type Curve struct {
	Frequency float64
	Damping   float64
}

var (
	// Snappy provides fast, tight, crisp transitions with minimal overshoot.
	Snappy = Curve{Frequency: 6.0, Damping: 0.9}

	// Organic provides smooth, responsive underdamped motion with natural settling.
	Organic = Curve{Frequency: 4.0, Damping: 0.7}

	// Elastic provides playful bounce for celebration badges and achievements.
	Elastic = Curve{Frequency: 3.5, Damping: 0.5}

	// Shake provides rapid oscillation for error/warning cues.
	Shake = Curve{Frequency: 8.0, Damping: 0.4}
)

// ReducedMotion checks if the user requested reduced motion via environment variables.
func ReducedMotion() bool {
	env := strings.ToLower(os.Getenv("RESUME_BUILDER_MOTION"))
	if env == "reduced" || env == "0" || env == "off" || env == "false" {
		return true
	}
	if os.Getenv("REDUCED_MOTION") == "1" || os.Getenv("RESUME_BUILDER_REDUCED_MOTION") == "1" {
		return true
	}
	return false
}

// Spring wraps harmonica.Spring with target tracking and convergence detection.
type Spring struct {
	spring  harmonica.Spring
	pos     float64
	vel     float64
	target  float64
	curve   Curve
	reduced bool
}

// NewSpring creates a Spring with the given curve, initial position, and target.
func NewSpring(curve Curve, initialPos, target float64) Spring {
	return Spring{
		spring:  harmonica.NewSpring(harmonica.FPS(60), curve.Frequency, curve.Damping),
		pos:     initialPos,
		vel:     0,
		target:  target,
		curve:   curve,
		reduced: ReducedMotion(),
	}
}

// Update advances the spring simulation by one 60fps tick.
// Returns current position and whether the spring has settled at target.
func (s *Spring) Update() (pos float64, settled bool) {
	if s.reduced {
		s.pos = s.target
		s.vel = 0
		return s.target, true
	}

	s.pos, s.vel = s.spring.Update(s.pos, s.vel, s.target)
	diff := s.pos - s.target
	if diff < 0 {
		diff = -diff
	}
	vel := s.vel
	if vel < 0 {
		vel = -vel
	}

	// Settling threshold: position within 0.1 and velocity near zero
	if diff < 0.1 && vel < 0.2 {
		s.pos = s.target
		s.vel = 0
		return s.target, true
	}

	return s.pos, false
}

// Pos returns current position.
func (s *Spring) Pos() float64 {
	return s.pos
}

// Target returns target position.
func (s *Spring) Target() float64 {
	return s.target
}
