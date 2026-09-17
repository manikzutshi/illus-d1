# Asset Registry Specification

The Asset Registry tracks all static and media files used for visualization, documentation, and simulation across the curriculum. It ensures that every visual or technical asset has clear provenance, licensing, and versioning.

## Asset Categories

- **2D Schematic Assets:** KiCad symbols, generic SVGs used for 2D schematic rendering.
- **3D Models:** GLB / glTF files for rendering components in the 3D visualization engine.
- **Technical Diagrams:** Block diagrams, state machine SVGs, curriculum illustrations.
- **Waveforms & Timing Diagrams:** Golden reference waveforms (e.g., VCD files or SVGs of expected I2C transactions).
- **Process / Package Visuals:** Micrographs, cross-sections, and 3D exploded views of semiconductor packages.
- **Datasheets & App Notes:** PDFs or markdown summaries of official manufacturer documentation.

## Asset Metadata Structure

Each asset entry will include:

- **Asset ID:** Unique identifier (e.g., `asset_3d_esp32_dev_v1`).
- **File Path:** Relative path within the `data/assets/` directory.
- **MIME Type / Format:** e.g., `model/gltf-binary`, `image/svg+xml`.
- **References:** Links to the original source if downloaded from a third party.
- **Provenance:** How the asset was created (e.g., "Modeled in Blender by internal team", "GrabCAD user XYZ").
- **License:** The legal license governing the asset (e.g., `CC-BY-4.0`, `MIT`, `Proprietary`).
- **Version:** Asset version to ensure cache invalidation and updates.
- **Associated Components:** Canonical IDs of components in the Component Registry that utilize this asset.
