---
name: enemy-swarm-ai
description: Melee chaser enemies in this pure-Python Ursina FPS (researched 2026-11-12, G18) - flow field pathfinding (cost grid -> Dijkstra integration field from the player -> per-cell direction, line-of-sight shortcut), time-sliced so a Python Dijkstra never costs a frame, boids-style local steering (separation, seek, flank offset), perception (vision cone + LOS ray, gunshot hearing), attack tokens limiting simultaneous attackers, telegraphed melee, and the per-frame CPU budget. Use when touching fps/core/flowfield.py, fps/core/enemies.py, fps/game/enemies.py, the Backrooms level, or adding any AI agent.
---

# Enemy swarm AI (researched 2026-11-12)

## Flow field (one field for the whole swarm)
- Pipeline: COST field (per cell, 255 = blocked) -> INTEGRATION field (cost-to-goal, Dijkstra outward from the goal cell) -> FLOW (each cell points at its cheapest neighbour). Cost is redone only when terrain changes; integration only when the goal (player cell) changes.
  Source: Emerson, "Crowd Pathfinding and Steering Using Flow Field Tiles", Game AI Pro ch.23 (abstract via https://www.taylorfrancis.com/books/9780429055096/chapters/10.1201/9780429055096-8 ; summary https://docs.rs/crate/bevy_flowfield_tiles_plugin/latest/source/README.md) - high - unverified.
- Cost scales with map size, not agent count: the right tool for 8-15+ chasers vs per-agent A*. Fieldrunners 2 used plain Dijkstra for the same reason; Theta*-like smoothing gives straighter paths. Source: https://therealcaleb116.github.io/GroupPathfindingWithFlowFields - medium - unverified.
- Line-of-sight shortcut: if the agent sees the goal directly, steer straight at it (ignore the grid). Source: https://github.com/vonwolfehaus/flow-field (blog-level) - medium - unverified.
- Project rules (decided G18):
  - Grid 0.5 m cells over the floor plan; per cell the walkable height (`Terrain.floor_at` at a probe height) and a blocked flag (solid box inflated by the agent radius).
  - Edge legal only if |height difference| <= step_up (the pool edge is a cliff: agents use the steps). Diagonal moves only if both orthogonal neighbours are open (no corner cutting).
  - Water depth adds cost (wading slow) so the swarm prefers the dry deck.
  - Numpy is NOT allowed at run time in this project: Dijkstra is pure Python with `heapq`, TIME-SLICED (a generator expanding N nodes per frame within ~1 ms). The old field is used until the new one finishes; a goal change restarts the job.
  - Direction for an agent = towards the cheapest of its 8 neighbours (ties: keep straight), blended with the LOS seek when the player is visible and close.

## Local steering (boids-style)
- Separation from neighbours inside 2 radii (spatial hash 2 m cells, O(n)), weight ~1.5; seek / flow weight 1; a per-agent flank offset (+-25-40 deg around the player) when within ~6 m so the group surrounds instead of queueing in a line. Reynolds steering behaviours (classic, high).
- Movement uses the same terrain physics as the player (`resolve_move`): walls, ledges and stairs cannot be cut by steering.

## Perception
- Vision: range + cone (~110 deg) + LOS ray against the static boxes; checked at ~5 Hz per agent with staggered phases (never all in one frame).
- Hearing: a gunshot alerts every agent within ~25 m (through walls); an alerted agent alerts neighbours within ~6 m. Once in CHASE an agent never loses the player in an arena level (action-game choice).

## Attack fairness: tokens (Doom 2016 pattern)
- An agent must take a token from a shared pool before attacking and returns it after; without one it circles / waits at the edge. Caps damage spikes so a crowd feels designed, not random. Sources: https://www.gamedeveloper.com/design/cyber-demons-the-ai-of-doom-2016- and https://www.strayspark.studio/blog/attack-token-system-ue5-group-combat-that-feels-fair - medium (secondary accounts of the GDC talk) - unverified.
- Melee must be TELEGRAPHED: wind-up (~0.35-0.5 s, visible lean / colour flash) -> strike only if still in reach and in front -> recovery / cooldown. Getting out of reach during the wind-up dodges it.

## State machine per agent
IDLE/PATROL (wander between random reachable cells) -> ALERT (heard / saw: turn, short delay) -> CHASE (flow field + steering) -> WINDUP -> STRIKE -> RECOVER -> CHASE; any state -> STAGGER on a hit (knockback, short stop) -> DEAD (fall, sink, fade, removed).

## Budget (Iris Xe laptop, Python)
- Target <= 2 ms CPU per frame for 15 agents: flow slice 1 ms, steering + movement 0.05 ms / agent, LOS rays staggered. Terrain queries must use a spatial grid (scanning every box per agent per frame costs ~0.15 ms / agent).

## Level theme reference: Backrooms Level 37 "Poolrooms"
- White ceramic tiles on floors, walls, stairs; shallow pools, some stairs dropping into deep pools; architecture "varied but strict", connections without purpose; uneven lighting with dark corners; muffled sound.
  Sources: https://backrooms.fandom.com/wiki/Level_37 , https://backrooms-pantheon.wikidot.com/level-37 - fan wiki (creative reference only) - medium.
