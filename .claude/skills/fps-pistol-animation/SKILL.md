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

## Two-hand grip reference (looked at images 2026-11-06, Bing image search; confidence: high for the pose, it is the standard "thumbs forward" grip)
Sources viewed: BC Firearms Academy "Proper Two Handed Handgun Grip", "Building A Thumbs Forward Grip" guides, Inside Safariland "Grip That Gun!" (front view), ArtStation "First Person Shooter Composition. Hands, Gloves, Glock", YouTube "Glock Viewmodel Animation (Type 2)".
- RIGHT hand: high on the backstrap, fingers wrapped around the front strap, index straight along the frame beside the trigger guard.
- LEFT hand: on the LEFT side of the grip, palm pressed against the frame's left side filling the gap, fingers wrap the front strap OVER/under the right-hand fingers (stacked), left thumb points FORWARD along the frame next to the right thumb. Left forearm comes in from the left-rear, roughly parallel to the right one.
- NOT the "cup and saucer" (left palm under the magazine) as the idle pose: that was my first attempt and looked wrong from the front.
- Reload: left hand LEAVES the grip, goes down to the magazine well, pulls the mag / seats the new one, comes back to the grip.
- Player-view check: render from the shooter's eye AND from the front; the front view exposes a hand that hangs in front of the gun.
