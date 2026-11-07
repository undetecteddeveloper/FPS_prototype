---
name: camera-easing-bezier
description: Cubic-bezier easing (CSS cubic-bezier timing functions) for camera / head motion in this project - how to evaluate it robustly (Newton + bisection), what the control points mean, and how fast a HEAD (not the eye) should move when looking around. Use when touching fps/core/easing.py, fps/core/gaze.py, the reload glance, or any eased camera move.
---

# Cubic-bezier easing for camera motion (researched 2026-11-07)

## The curve (CSS cubic-bezier(x1, y1, x2, y2))
- Endpoints fixed at P0 = (0, 0), P3 = (1, 1); P1 = (x1, y1), P2 = (x2, y2). x = time progress, y = output progress.
  x1 and x2 MUST be in [0, 1] (otherwise the curve is not monotonic in time); y1, y2 are free: y > 1 or < 0 gives overshoot / anticipation inside the curve itself.
  Outside [0, 1] input, CSS extends the curve along the end tangents (we just clamp the input).
  Source: W3C CSS Easing Functions L1 https://www.w3.org/TR/css-easing-1 and draft https://drafts.csswg.org/css-easing-1/ - high - verified-in-project (tests/test_easing.py).
- Evaluate: per axis B(t) = 3(1-t)^2 t P1 + 3(1-t) t^2 P2 + t^3 (polynomial form a t^3 + b t^2 + c t with c = 3 P1, b = 3 (P2 - P1) - c, a = 1 - c - b).
  Given input x, solve x(t) = x for t, then output y(t).
- Solving (browser approach): ~8 Newton-Raphson steps from a good guess, stop when |x(t) - x| < eps, give up on Newton when |x'(t)| is tiny, then fall back to bisection on [0, 1].
  Chromium also seeds the guess from a sampled table. Source: Chromium ui/gfx/geometry/cubic_bezier.cc https://chromium.googlesource.com/chromium/src/+/dfe9acda5/ui/gfx/geometry/cubic_bezier.cc ;
  Rust ports https://docs.rs/eazy-core/latest/src/eazy_core/easing/bezier/cubic_bezier.rs.html - high - verified-in-project (tests/test_easing.py: monotonic, endpoints, inverse accuracy).
- Useful shapes: ease-in-out (0.42, 0, 0.58, 1); "slow start, long soft landing" (0.45, 0, 0.15, 1); small settle overshoot (0.4, 0, 0.3, 1.06).

## How fast a head moves (the camera is a head / chest cam, not an eye)
- Gaze shifts under ~20 deg are done almost entirely by the EYES; the head barely moves. Above ~20-25 deg the head contributes more with amplitude.
  The head starts 20-40 ms after the eye saccade. Source: monkey/human eye-head coordination studies, e.g. https://pmc.ncbi.nlm.nih.gov/articles/PMC2276249 , J Neurophysiol 1995 https://www.sciencegate.app/document/10.1152/jn.1995.73.2.766 - medium - unverified (abstracts).
- Eye peak velocity ~290 deg/s at 10 deg, ~400 deg/s at 20 deg; head peak velocity grows linearly with amplitude (Acta Oto-Laryngologica 1980 https://informahealthcare.com/doi/abs/10.3109/00016488009131715 - medium - unverified).
  A common model uses a ~400 ms head movement (https://www.cis.rit.edu/people/faculty/pelz/dissertation/chap4/index.html - low, model assumption).
- Game consequence: a head-cam "glance" must be slow (0.3-0.5 s), eased, and rest long (0.6-0.9 s) between glances; eye-speed glances (< 0.15 s) read as jitter.
  verified-in-project: user feedback 2026-11-07 ("camera không nhìn đủ lâu ... giật giật"), fixed in fps/core/gaze.py.
