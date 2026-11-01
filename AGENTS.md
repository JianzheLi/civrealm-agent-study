# CivRealm Agent Study workspace

- The user authorized a new independent repository for the overall project framework, README and later group collaboration.
- The user explicitly authorized implementing and running jianzheli's two development tasks on 2026-11-01: 100 normal scenes per task, real statistics, cases and visualizations. API spending has no total cap for this requested run; retain complete usage records. Do not invent results or import old conclusions.
- Focus on task 2: LLM agents across CivRealm tasks, failure/behavior diagnosis, targeted improvements and independent evaluation. The user selected five normal-difficulty tasks: two development, two battle and one diplomacy. Do not add RL-based training or comparisons to the current scope.
- The user confirmed 100 first-stage diagnosis instances per task, 500 in total, using the five default task names in README. Reusing a 20-instance development subset and reserving 50 independent test instances per task remain recommendations. First collect a consistent baseline diagnosis set, then propose improvements.
- The user prefers broad observation and natural resource-use comparison: no independent per-episode API-call cap; default to a wide 2,000-env-step stopping line and preserve native turn/terminal rules. Record all calls, including correction, reflection and actual retries. Do not include project cumulative API-budget discussion in the shared guide. This editorial change does not authorize launching paid experiments or changing the session spending authorization.
- README must be a practical group guide: stages, concrete work, deliverables, required records, comparison metrics and documentation entry points. Preserve its workflow diagram and keep work division last. Do not add imaginary runnable commands.
- Current work is first-round trajectory collection/statistics, failure-case analysis and real visualizations, before proposing improvements. Required visual outputs belong in docs/first_round_analysis.md; do not invent plots or results before this round produces data.
- All tasks must use the latest DeepSeek model verified from official sources at the start of the round; as of 2026-11-01 this is DeepSeek-V4.1-Flash-1017 through deepseek-flash. Record the actual model/version and date, and separate batches if the serving version changes.
- Keep assigned work division last in README: jianzheli owns the two development tasks (200 episodes), songluo owns the two battle tasks (200), beibeideng owns diplomacy (100). Each owns collection, statistics, failure cases and visualizations for their category. Do not contact or invite members unless instructed.
- Keep the prior `civilization` workspace unchanged. This repository is independent.
- Follow the user's scope limits: fix actual issues, avoid speculative defenses, extra wrappers, checksum files and unnecessary tests. Before a check, identify the failure it detects and the action it changes.
- Preserve evidence boundaries: distinguish proposed methods, observed patterns and effects established by controlled experiments. Keep task definitions identical across compared agents unless explicitly varied.
- Keep credentials out of source and logs. Use DEEPSEEK_API_KEY. Models, savegames, raw trajectories and caches remain outside Git; configuration and compact summaries are versioned.
- Keep module interfaces in docs/interfaces.md, detailed logging/counting in docs/logging_spec.md, experimental conventions in docs/experiment_protocol.md and task-specific semantics in docs/tasks/. Keep parameter values consistent with docs/llm_study_design.md.
- All runnable commands and implementation claims must correspond to actual files. Shared implementation lives in src/civstudy; only the two development task specifications and collection are implemented in this request. The other members' tasks remain outside this execution.
- No proactive subagents or unsolicited teammate messages/invitations.
- On 2026-11-01 the user additionally authorized downloading the worthwhile representative raw trajectories and videos locally. The curated review subset lives under runs/local_review/ (outside Git), with explanations and portable browsing pages in reports/failure_diagnosis/. The user explicitly chose to retain the current thinking/high + 8192 generation budget and continue organizing existing results; do not change the collection configuration or launch a new experiment as part of this review.
- On 2026-11-02 the user requested native Freeciv game screenshots for successful and failed examples. Recorded-action reenactments are authorized without new LLM requests; exact agreement with the original trajectory is not required. Keep them separate from formal results and identify them as new demonstrations. Close dialogs, enlarge the map, and show the final game state without success/failure popups. Native captures and provenance live in reports/native_examples/; source is src/civstudy/native_examples.py.

## Directory guide

- docs/: shared contracts, logging/counting specification, first-round analysis/visualization guide, experiment protocol and task specifications.
- configs/: experiment settings and fixed instance manifests; see its README.
- prompts/: versioned prompts and variant notes.
- src/: shared environment, agent, runner, analysis and state-replay implementation.
- scripts/: deployment and reproducible command entry points.
- reports/: compact figures, case studies, video indices and report sources.
