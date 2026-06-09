# GitHub Release Audit: 2026-06-09

Release checked:

```text
repository: Danchik757/Mesh-Saliency-Projection
tag: v1.0-data
published: 2026-06-01T14:45:54Z
```

## Result

`v1.0-data` is readable but is not approved as the source for the next benchmark
generation.

All 12 downloaded ZIP files pass ZIP CRC validation. That proves archive
integrity, not semantic correctness.

## Blocking Findings

1. New `processed_fixations_offset_2000` JSONs are absent.
2. `camera_jsons.zip` contains 299 JSONs, but all 57 SAL3D JSONs differ
   semantically from the corrected repository-local SAL3D placement JSONs.
3. `3dva_combined_gt.zip` is referenced by repository documentation and download
   scripts but is absent from the actual release.
4. `gaze_csv_sal3d.zip` exists in the release but is absent from the current
   `package_datasets.sh` and `download_datasets.sh` contract.
5. `sal3d_smooth_gaze.zip` contains only 5 files under `Smooth Gaze/`, while the
   current code/docs expect `Smooth_Gaze/` and broader coverage.
6. The release has no machine-readable manifest or SHA-256 checksum file.
7. MeshMamba OBJ archives contain 106 OBJ files for 105 model tracks because of
   an extra nested duplicate; model-to-OBJ mapping must be validated rather than
   inferred from OBJ count.
8. `meshmamba_saliency_gt.zip` contains 213 CSVs plus one Python script; expected
   benchmark GT coverage must be explicitly mapped.

## Release Inventory

| Asset | Files | Important observation |
| --- | ---: | --- |
| `3dva_gt.zip` | 1440 TXT | CRC valid |
| `3dva_objs.zip` | 32 OBJ | CRC valid |
| `camera_jsons.zip` | 299 JSON | 57 corrected SAL3D versions missing |
| `gaze_csv_3dva.zip` | 32 CSV | CRC valid |
| `gaze_csv_meshmamba.zip` | 210 CSV | 105 + 105 |
| `gaze_csv_sal3d.zip` | 56 CSV | not handled by current package/download scripts |
| `meshmamba_non_texture_objs.zip` | 106 OBJ plus metadata/embedded ZIP | needs mapping audit |
| `meshmamba_rgb_texture_objs.zip` | 106 OBJ plus texture assets | needs mapping audit |
| `meshmamba_saliency_gt.zip` | 213 CSV + 1 PY | needs mapping audit |
| `sal3d_gaze.zip` | 58 TXT | 57 meshes; known extra gaze files |
| `sal3d_meshes.zip` | 57 OBJ | CRC valid |
| `sal3d_smooth_gaze.zip` | 5 TXT | incomplete/incompatible path contract |

## SHA-256

```text
3ecf0c5f77f0a79c0c5beefc2697f5601bb2962e43ebbc199fcd0d99d88d5428  3dva_gt.zip
7c0aad8b5bc910ca22d65cefda5d81bdb2c07cce9f30ce9e2be5a7160e448c5a  3dva_objs.zip
bd7de90dc54625235165605d9d5dd8f342dd8dfae5f756ea0f685077ba733869  camera_jsons.zip
b7a6fd284f680d802a69d9246e8037dfbc22454fc10b7aa710890ce596dc70fa  gaze_csv_3dva.zip
bd3f1df9223c0a6d3ae4cc789201b5fadd7dc431bd7f8465235109373c41ca90  gaze_csv_meshmamba.zip
36ce9947bbddf6202a831adc7038bbaef333e5fb1fd5bfb25331aea6b7e6bcd5  gaze_csv_sal3d.zip
7b053cdb7bde4605dd505343a40321fe25d745bd3edfbac7e140e07d4816fc20  meshmamba_non_texture_objs.zip
a6ca180cbe34a4e1ee7b13f5760e44c61f8fed525a79a2d50a8bb95d8806eb8b  meshmamba_rgb_texture_objs.zip
4567282ae6e040b544631ec32528c0f093a8893e933b9d6d9ca458504b1156f2  meshmamba_saliency_gt.zip
9c761c202c8a185446f8c8435c0ae96b59b3ca2ab20836dfc1b6bfec458841c0  sal3d_gaze.zip
cdcb1983cb95abb5a62f55229961438047e7df68582d1d06b8034e87cf8a3816  sal3d_meshes.zip
fc491e2996443190ed4792bdca0445e86321d25d2a87b0fcb5cdf8681311ddb0  sal3d_smooth_gaze.zip
```

## Release Acceptance Gate

A replacement release candidate is accepted only when:

1. every archive passes CRC validation;
2. a manifest lists expected and actual files per dataset/track;
3. canonical placement JSONs match repository files semantically;
4. processed fixation files pass frame/coordinate validation;
5. known invalid/missing objects are explicitly excluded or repaired;
6. a clean-machine extraction smoke test passes;
7. one model per dataset/track completes a projection/metric smoke test from
   release-only inputs.
