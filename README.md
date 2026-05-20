# Mesh-Saliency-Projection

Repository for the main codebase of the mesh saliency projection project.

Current focus:

- organize reprojection pipelines used in the project;
- keep trusted metric implementations in one place;
- compare screen-space and mesh-space saliency transfer methods;
- keep visualization and evaluation scripts inside one structured repository.

Main folders:

- [metrics](./metrics/README.md)
- [reprojection_methods](./reprojection_methods/README.md)
- [video_creation](./video_creation/README.md)
- [requirements](./requirements/README.md)
- [datasets](./datasets/README.md)
- [docs](./docs/project_structure.md)

Dataset reference table:

- [Google Sheets dataset table](https://docs.google.com/spreadsheets/d/1UpTHzfqAma46_czqMvlA_15AVIm5T2Em6d_BmskiCkQ/edit?gid=881515507#gid=881515507)

Notes:

- raw datasets are expected to stay outside the repository;
- generated outputs should go into `results/`;
- method-specific documentation is stored inside `reprojection_methods/`.
