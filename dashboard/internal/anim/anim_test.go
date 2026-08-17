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
