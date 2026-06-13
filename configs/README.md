# Configs

Store reproducible run configurations here:

- dataset paths
- train/test splits
- sigma presets
- rendering presets
- output locations

`server_vg_intellect.env` is the current server template. It uses only
`/mnt/ssd1/29d_kon/acm_2026`, separates processed fixation JSON from original
CSV compatibility inputs, and expects data extracted from a validated v2 GitHub
Release candidate. The default template targets `v2.0-data-rc4`, offset0
processed fixations, and the `one_turn_from_start` baseline contract.
