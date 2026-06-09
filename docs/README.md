# docs/

Project documentation: architecture notes, dataset-specific evaluation notes,
and benchmark runbooks.

| File | Contents |
|------|----------|
| [EVAL_RUNBOOK.md](./EVAL_RUNBOOK.md) | Current commands, flags, and path conventions for running evaluations |
| [project_structure.md](./project_structure.md) | High-level architecture, module responsibilities, data flow |
| [3DVA_COMBINED_GT_IMPLEMENTATION.md](./3DVA_COMBINED_GT_IMPLEMENTATION.md) | Combined-GT pipeline for 3DVA and batch-run details |
| [3DVA_VERIFICATION_METHOD.md](./3DVA_VERIFICATION_METHOD.md) | How 3DVA alignment and GT comparisons were validated |
| [AGENT_INSTRUCTION_3DVA_ANALYSIS.md](./AGENT_INSTRUCTION_3DVA_ANALYSIS.md) | 3DVA-specific operating notes for future agents |
| [../jsons/README.md](../jsons/README.md) | Canonical repository-local JSON layout and validation rules |

## Notes

- `trash/Claude.md` and `trash/GPT.md` are append-only work logs. They preserve
  session history, but they are not the authoritative source for the current
  pipeline configuration.
- The old one-file handoff note was removed because it drifted out of sync with
  the code and duplicated material now covered by the files above.
