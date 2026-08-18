package anim

import (
	"os"
	"testing"
)

func TestSpringConvergence(t *testing.T) {
	curves := []struct {
		name  string
		curve Curve
	}{
		{"Snappy", Snappy},
		{"Organic", Organic},
		{"Elastic", Elastic},
		{"Shake", Shake},
	}

	for _, tc := range curves {
		t.Run(tc.name, func(t *testing.T) {
			s := NewSpring(tc.curve, 0, 100)
			settled := false
			var pos float64
			for frame := 0; frame < 300; frame++ {
				pos, settled = s.Update()
				if settled {
					break
				}
			}

			if !settled {
				t.Fatalf("expected spring %s to settle within 300 frames, final pos: %f", tc.name, pos)
			}
			if pos != 100 {
				t.Fatalf("expected final pos 100, got: %f", pos)
			}
		})
	}
}

func TestReducedMotion(t *testing.T) {
	os.Setenv("RESUME_BUILDER_MOTION", "reduced")
	defer os.Unsetenv("RESUME_BUILDER_MOTION")

	if !ReducedMotion() {
		t.Fatalf("expected ReducedMotion() to be true when env is set")
	}

	s := NewSpring(Organic, 0, 50)
	pos, settled := s.Update()
	if !settled {
		t.Fatalf("expected spring to settle immediately with reduced motion")
	}
	if pos != 50 {
		t.Fatalf("expected immediate snap to target 50, got: %f", pos)
	}
}

func TestConfettiEngine_ParticleEmission(t *testing.T) {
	os.Unsetenv("RESUME_BUILDER_MOTION")
	engine := NewConfettiEngine(80, 24)
	if engine.Active() {
		t.Fatalf("expected initial engine to be inactive")
	}

	engine.Emit(40, 12, 30)
	if !engine.Active() {
		t.Fatalf("expected engine to be active after emit")
	}
	if len(engine.Particles()) < 20 {
		t.Fatalf("expected at least 20 particles emitted, got %d", len(engine.Particles()))
	}

	// Step frames until exhausted
	active := true
	for frame := 0; frame < 100; frame++ {
		active = engine.Update()
		if !active {
			break
		}
	}

	if active {
		t.Fatalf("expected confetti particles to finish within 100 frames")
	}
	if len(engine.Particles()) != 0 {
		t.Fatalf("expected 0 remaining particles after completion")
	}
}

func TestConfettiEngine_ReducedMotion(t *testing.T) {
	t.Setenv("RESUME_BUILDER_MOTION", "reduced")
	engine := NewConfettiEngine(80, 24)
	engine.Emit(40, 12, 30)
	if engine.Active() || len(engine.Particles()) > 0 {
		t.Fatalf("expected zero particles emitted when reduced motion is enabled")
	}
}

func TestSpringCursor_KineticInterpolation(t *testing.T) {
	os.Unsetenv("RESUME_BUILDER_MOTION")
	cursor := NewSpringCursor(0)
	cursor.SetTarget(5)

	var lastPos float64
	for frame := 0; frame < 60; frame++ {
		pos, settled := cursor.Update()
		if frame > 0 && pos < lastPos {
			t.Fatalf("expected monotonically approaching cursor, got frame %d: pos %f < last %f", frame, pos, lastPos)
		}
		lastPos = pos
		if settled {
			break
		}
	}

	if lastPos != 5.0 {
		t.Fatalf("expected final settled cursor pos 5.0, got %f", lastPos)
	}
}
