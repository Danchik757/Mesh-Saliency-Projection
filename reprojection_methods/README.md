# Reprojection Methods

This folder stores the point-transfer methods currently used in the project.

Implemented methods:

- [screen_space_gaussian](./screen_space_gaussian/README.md)
- [cone_projection_on_mesh](./cone_projection_on_mesh/README.md)

The two methods solve different versions of the same problem:

- start from raw gaze / fixation data;
- build a dense saliency map;
- compare the produced map to a target map or to held-out fixation data.
