---
name: fps-pistol-animation
description: Design notes for first-person pistol viewmodel animation sets - states, reload with and without slide lock, timing events. Use when planning or authoring Glock clips.
---
# Pistol viewmodel animation design (2026-11-06; forum-level sources, low confidence, unverified)
- Clips needed: idle (loop), draw, holster, fire (slide back+forward; on the LAST round the slide stays locked back), reload (mag out -> mag in -> slide release/forward only if chambered round absent), reload_empty (slide locked back: mag out -> mag in -> press slide stop / rack). Tactical reload (round in chamber) does NOT touch the slide.
- Event frames per clip like the M4 `Clip`: `swap` = frame the new mag seats; `settle` = hands back at rest. Add `slide_release` frame for reload_empty. Mag, slide, trigger are separate parts so code can hide/show spare mag.
- State flags (forum pattern): reloading / mag_loaded / chambered. Gate firing until the clip's settle frame.
- Quality bar: no pops at clip start/end, mag lines up with the well through the move.
- Sprint pose, ADS pose, bob: code-driven offsets in weapon_data (existing M4 systems), not baked clips.
- Real timing not found online; tune by feel with the F1 panel.
