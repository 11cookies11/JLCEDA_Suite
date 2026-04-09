# Changelog

Language: English | [简体中文](CHANGELOG.zh-CN.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
