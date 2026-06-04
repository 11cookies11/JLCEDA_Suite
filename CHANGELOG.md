# Changelog

Language: English | [绠€浣撲腑鏂嘳(CHANGELOG.zh-CN.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-06-05

### Changed

- Removed symbol fallback paths so missing or mismatched KiCad symbols now fail explicitly instead of silently generating placeholder parts.
- Refreshed the verified `esp32c3-minimal-system` and `stm32f103-minimal-system` examples to the current protocol and release layout.
- Synced the Python package metadata version with the release-ready `package.json` version.

## [0.1.28] - 2026-05-11

### Fixed

- Improved remote bridge connection resilience by treating heartbeat and response send failures as transport failures that trigger reconnect.
- Disabled server-side WebSocket protocol heartbeat by default to avoid incompatibility with the JLCEDA WebSocket runtime while keeping application-level heartbeats.
- Updated bridge smoke coverage for heartbeat failure reconnect behavior.

## [0.1.27] - 2026-04-12

### Added

- Added a Python multipage placement validation script (`server_placement_multipage_test.py`) to verify placement behavior from simple to dense scenarios.
- Added a generic circuit-model to execution-plan compiler (`compile_execution_plan.py`) and a companion mapping guide.

### Fixed

- Improved schematic placement collision avoidance by adding a runtime occupancy check before finalizing candidate coordinates.

## [0.1.26] - 2026-04-09

### Fixed

- Added an `XMLHttpRequest` fallback for GitHub release checks so plugin auto-update works in JLCEDA runtimes where `fetch` is unavailable
- Kept the 0.1.24 shell-menu label fix and suite release asset layout

## [0.1.24] - 2026-04-09

### Fixed

- Replaced host-menu labels with ASCII-safe titles (`Introduction`, `Open Console`) to avoid `???` rendering in the JLCEDA shell
- Kept the extension-manager metadata packaging fix from 0.1.23 so README-based detail content remains available in packaged builds

## [0.1.23] - 2026-04-09

### Fixed

- Included `README.md` and `README.zh-CN.md` in packaged extension bundles so extension managers can render plugin details pages
- Added suite homepage and issue tracker links to the extension manifest metadata
## [0.1.22] - 2026-04-09

### Added

- Added a dedicated plugin introduction page and bundled suite icon so first-time users can understand the package before opening the console

### Changed

- Renamed the project branding from JLCEDA AIAgent to JLCEDA Suite across the plugin, server defaults, update settings, and release artifacts
- Split the suite naming into `JLCEDA Suite Plugin`, `JLCEDA Suite Server`, and `JLCEDA Suite Skill`
- Renamed the bundled skill package and release bundle outputs to the `jlceda-suite-*` naming scheme

## [0.1.21] - 2026-04-09

### Added

- Server-side rule profiles for schematic and PCB heuristics, with profile endpoints for inspection and switching
- Plugin-side profile-aware thresholds for placement avoidance, label hygiene, PCB hygiene, and power-block suggestions
- Stable plugin execution-layer baseline guidance so future tuning can stay in the server profile layer

### Changed

- Remote bridge configuration now includes a separate control-plane URL and token, with automatic derivation from the server URL when possible

### Fixed

- Schematic placement, label placement, and power-block heuristics now read their tunable parameters from the active server profile instead of hardcoded constants

## [0.1.20] - 2026-04-09

### Fixed

- Added a source-level fallback path for `pcb.place_footprint` to avoid the current JLCEDA runtime object-conversion failure in `pcb_PrimitiveComponent.create`
- Added smoke-test coverage for both the direct PCB placement path and the fallback path

## [Unreleased]
