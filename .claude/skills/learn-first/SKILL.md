---
name: learn-first
description: Protocol to run BEFORE starting any non-trivial task in this project (modeling, rigging, animation, shaders, audio, networking, tooling...). Check for an existing knowledge skill for the topic, research deeply when missing, and save what was learned as a compact skill so later sessions do not forget it.
---

# Learn first, then save, then work

Goal: knowledge learned from the web survives across sessions. Rule from the user (2026-11-06): learn once, store it, look it up later; re-learn only the missing parts.

## 1. Check
- List `.claude/skills/*/SKILL.md` descriptions. If a skill covers the topic and the needed sub-topic, USE it and stop here.
- If it exists but lacks the needed part, research only the missing part and extend that skill.

## 2. Research (topic missing)
- Use WebSearch (standard first; extended for niche or very recent facts) and official docs. Prefer primary sources (manuals, API references, vendor docs) over blog posts.
- Learn deeply enough to do the task correctly: concepts, parameters, pitfalls, conventions, version differences. For modeling that means mesh/topology, UV/texture, rigging, skinning, animation, glTF export, and this project's engine conventions.
- Run subagents in parallel for independent sub-topics when it pays off (disjoint skill folders, cheap model for mechanical summarizing).

## 3. Save BEFORE working
- One skill per topic: `.claude/skills/<short-topic-name>/SKILL.md`. Split a big topic into several small skills.
- Write in English, dense, for Claude as the reader. No Vietnamese summary needed.
- Size is your call: judge the topic's importance and complexity. Keep `SKILL.md` lean (a description precise enough to be auto-loaded, core rules, pitfalls). Put long detail in `references/*.md` that is opened only when needed.
- Frontmatter: `name` and a `description` stating what the skill covers and when to use it.
- Every claim carries: source URL, date read, confidence (high / medium / low), status `unverified` or `verified-in-project` (name the experiment). Record tool versions (for example Blender 5.1, extension 1.0.0). When sources disagree, record both.

## 4. Verify what matters
- Test important claims with a small experiment in this project, then upgrade the status to `verified-in-project` and name the experiment. Wrong claims get corrected, not deleted silently.

## 5. Report
- End of session: say which skills were created or updated.
