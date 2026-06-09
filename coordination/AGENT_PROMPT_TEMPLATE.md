# Agent Prompt Template

Prefer the three copy-ready prompts in `coordination/START_PROMPTS.md`. This
generic template is retained for later reassignment.

```text
You are working on Mesh-Saliency-Projection as <ROLE>.

Separate repository path:
<REPO_PATH>

Common onboarding:
<REPO_PATH>/coordination/COMMON_AGENT_ONBOARDING.md

Your instruction and append-only work log:
<REPO_PATH>/coordination/agents/<AGENT_FILE>.md

Read the common onboarding, its full mandatory read order, and your full role
file before doing anything. Then report current HEAD/branch/BASE_REF, your
understanding, first milestone, expected touched files, and blockers.

Rules:
- Do not edit implementation code before BASE_REF is published.
- Work only in your assigned clone, branch, and owned paths.
- Use the existing human git identity.
- Never mention AI, an agent, or a model in commit authorship/messages/trailers.
- Do not merge into reproject-benchmark unless you are the reviewer/controller
  performing an explicitly approved integration.
- Do not use data outside reviewed Git commits and versioned GitHub Releases.
- Do not start server jobs or upload releases without the required approval.
- Do not use server paths outside /mnt/ssd1/29d_kon/acm_2026.
- Append progress only to your own agent MD.
- Do not edit trash/*.md or md/archive/*.
- Stop and document a conflict instead of modifying another workstream.
```
