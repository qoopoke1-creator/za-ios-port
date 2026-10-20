# Z-A iOS port research

This repository is based on [seedds/nxnative](https://github.com/seedds/nxnative)
at upstream commit `a35e96437f48bbbfbde40b7a133ef6681c2fbc1c`.
Upstream code and third-party components retain their original licenses and attribution.
The upstream README describes upstream functionality, not Z-A compatibility.

## Current scope

- Windows extraction and static analysis using locally supplied resources.
- `scripts/survey_extracted.py` surveys an existing ExeFS and RomFS manifest without Xcode.
- `.github/workflows/ci-environment.yml` probes a standard ARM64 macOS runner,
  Xcode, iOS Metal compilation and optional macOS Metal availability.
- Z-A has not been built or run on iOS by this project.
- Static survey results indicate that the main resource archive requires further analysis.

No game packages, extracted resources, rewritten game binaries, game shaders, keys,
saves or game-containing IPAs are included. Keep all such inputs and outputs outside
this source repository. Do not upload them as public workflow artifacts.

The environment workflow accepts no game inputs or credentials and produces no IPA.
Its success only establishes the toolchain capabilities tested by its steps.
