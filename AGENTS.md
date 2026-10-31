# CivRealm Agent Study workspace

- The user authorized a new independent repository for the overall project framework, README and later group collaboration.
- Current scope is framework and documentation. Do not launch experiments, spend API credits, invent results or copy old experimental conclusions into this repository unless the user asks.
- Focus on task 2: LLM agents across CivRealm tasks, failure/behavior diagnosis, targeted improvements and independent evaluation. The user selected five normal-difficulty tasks: two development, two battle and one diplomacy. Do not add RL-based training or comparisons to the current scope.
- The user confirmed 100 first-stage diagnosis instances per task, 500 in total, using the five default task names in README. Reusing a 20-instance development subset and reserving 50 independent test instances per task remain recommendations. First collect a consistent baseline diagnosis set, then propose improvements.
- The user prefers broad observation and natural resource-use comparison: no independent per-episode API-call cap; default to a wide 2,000-env-step stopping line, preserve native turn/terminal rules and the cumulative USD 50 project limit. Record all calls, including correction, reflection and actual retries. Limits and counting semantics belong in docs/llm_study_design.md and docs/logging_spec.md.
- README must be a practical group guide: stages, concrete work, deliverables, required records, comparison metrics and documentation entry points. Preserve its workflow diagram and keep work division last. Do not add imaginary runnable commands.
- Discuss the overall framework first. Any work division belongs at the end of the main README and remains unassigned until the group decides.
- Keep the prior `civilization` workspace unchanged. This repository is independent.
- Follow the user's scope limits: fix actual issues, avoid speculative defenses, extra wrappers, checksum files and unnecessary tests. Before a check, identify the failure it detects and the action it changes.
- Preserve evidence boundaries: distinguish proposed methods, observed patterns and effects established by controlled experiments. Keep task definitions identical across compared agents unless explicitly varied.
- Keep credentials out of source and logs. Use DEEPSEEK_API_KEY. Models, savegames, raw trajectories and caches remain outside Git; configuration and compact summaries are versioned.
- Keep module interfaces in docs/interfaces.md, detailed logging/counting in docs/logging_spec.md, experimental conventions in docs/experiment_protocol.md and task-specific semantics in docs/tasks/. Keep parameter values consistent with docs/llm_study_design.md.
- All runnable commands and implementation claims must correspond to actual files. At this stage the repository is documentation only.
- No proactive subagents or unsolicited teammate messages/invitations.

## Directory guide

- docs/: shared contracts, logging/counting specification, experiment protocol and task specifications.
- configs/: future experiment settings and instance manifests; see its README.
- prompts/: versioned prompts and variant notes.
- src/: future environment, agent, runner, trace and analysis implementation.
- scripts/: future reproducible command entry points.
- reports/: future compact figures, case studies and report sources.
