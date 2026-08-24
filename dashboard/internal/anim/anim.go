// Package anim provides harmonica-powered spring physics curves and reduced-motion gating for TUI interfaces.
package anim

import (
	"math"
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

// SetTarget updates the target position.
func (s *Spring) SetTarget(target float64) {
	s.target = target
}

// Particle represents an individual celebration or sparkle particle.
type Particle struct {
	X, Y     float64
	Vx, Vy   float64
	Glyph    rune
	ColorHex string
	Life     int
	MaxLife  int
}

// ConfettiEngine manages physics particles for celebratory events and achievements.
type ConfettiEngine struct {
	particles []Particle
	width     int
	height    int
	active    bool
}

// NewConfettiEngine creates an engine bounded by screen dimensions.
func NewConfettiEngine(width, height int) *ConfettiEngine {
	return &ConfettiEngine{
		particles: make([]Particle, 0),
		width:     width,
		height:    height,
		active:    false,
	}
}

// Active returns whether particles are currently alive.
func (c *ConfettiEngine) Active() bool {
	return c.active
}

// Particles returns the slice of current live particles.
func (c *ConfettiEngine) Particles() []Particle {
	return c.particles
}

// Clear clears all live particles.
func (c *ConfettiEngine) Clear() {
	c.particles = c.particles[:0]
	c.active = false
}

// Emit spawns a burst of particles from the given origin coordinate.
func (c *ConfettiEngine) Emit(x, y, count int) {
	if ReducedMotion() {
		return
	}
	glyphs := []rune{'✦', '✧', '★', '◆', '●', '■', '•', '✢'}
	colors := []string{"#cba6f7", "#89b4fa", "#a6e3a1", "#f9e2af", "#f38ba8", "#fab387"}

	for i := 0; i < count; i++ {
		angle := float64(i) / float64(count) * 2 * math.Pi
		speed := 0.5 + float64(i%5)*0.3
		vx := math.Cos(angle) * speed * 2.0
		vy := math.Sin(angle)*speed - 0.5
		glyph := glyphs[i%len(glyphs)]
		colorHex := colors[i%len(colors)]
		life := 20 + (i % 15)

		c.particles = append(c.particles, Particle{
			X:        float64(x),
			Y:        float64(y),
			Vx:       vx,
			Vy:       vy,
			Glyph:    glyph,
			ColorHex: colorHex,
			Life:     life,
			MaxLife:  life,
		})
	}
	c.active = len(c.particles) > 0
}

// Update advances particle positions and gravity. Returns true if particles remain.
func (c *ConfettiEngine) Update() bool {
	if !c.active || len(c.particles) == 0 {
		c.active = false
		return false
	}

	alive := make([]Particle, 0, len(c.particles))
	for _, p := range c.particles {
		p.Life--
		if p.Life <= 0 {
			continue
		}
		p.X += p.Vx
		p.Y += p.Vy
		p.Vy += 0.05
		p.Vx *= 0.95

		alive = append(alive, p)
	}

	c.particles = alive
	c.active = len(c.particles) > 0
	return c.active
}

// SpringCursor smoothly interpolates cursor movements in lists and menus.
type SpringCursor struct {
	spring Spring
	target int
}

// NewSpringCursor creates a new spring-damped cursor.
func NewSpringCursor(initialIndex int) *SpringCursor {
	return &SpringCursor{
		spring: NewSpring(Snappy, float64(initialIndex), float64(initialIndex)),
		target: initialIndex,
	}
}

// SetTarget sets the new target index.
func (sc *SpringCursor) SetTarget(targetIndex int) {
	sc.target = targetIndex
	sc.spring.target = float64(targetIndex)
}

// Update advances the cursor spring by one tick.
func (sc *SpringCursor) Update() (float64, bool) {
	return sc.spring.Update()
}

// CurrentPos returns the current fractional cursor position.
func (sc *SpringCursor) CurrentPos() float64 {
	return sc.spring.Pos()
}
