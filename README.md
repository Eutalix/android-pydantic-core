# 📱 Android Pydantic Core

[![Build & Release](https://img.shields.io/github/actions/workflow/status/Eutalix/android-pydantic-core/build_wheels.yml?label=Build)](https://github.com/Eutalix/android-pydantic-core/actions/build_wheels.yml)
[![Architectures](https://img.shields.io/badge/arch-arm64--v8a%20%7C%20armeabi--v7a%20%7C%20x86%20%7C%20x86__64-orange)](https://github.com/Eutalix/android-pydantic-core/releases)

**Automated builds of `pydantic-core` for Android, tested against real Termux.**

Compiling `pydantic-core` on-device requires a Rust toolchain and takes
several minutes (or fails outright due to memory limits). This repository
cross-compiles it in CI and publishes ready-to-install wheels.

## 📦 Supported Targets

| Android ABI | `uname -m` on device | Status |
|-------------|-----------------------|--------|
| `arm64-v8a` | `aarch64` | ✅ Supported |
| `armeabi-v7a` | `arm` | ✅ Supported |
| `x86_64` | `x86_64` | ✅ Supported |
| `x86` | `i686` | ✅ Supported |

> **Python version:** this repo tracks a single, rolling Python version —
> whichever major.minor `python` package Termux's own `pkg`/`apt`
> repository currently serves. There is no parallel 3.9–3.13 matrix.
> Older wheels remain available under
> [Releases](https://github.com/Eutalix/android-pydantic-core/releases)
> if you haven't run `pkg upgrade python` yet.

---

## 🚀 Installation

### ⚡ Option 1: Quick Install (Script)

Auto-detects your architecture and installed Python version.

```bash
curl -sL https://raw.githubusercontent.com/Eutalix/android-pydantic-core/main/install_pydantic_core.sh | bash
```

### 🐍 Option 2: Pip (Standard)

Best for requirements files or CI/CD.

```bash
pip install pydantic-core --extra-index-url https://eutalix.github.io/android-pydantic-core/
```

### 📦 Option 3: Manual Download

Download the `.whl` matching your Python ABI tag and Android ABI from the
[Releases Page](https://github.com/Eutalix/android-pydantic-core/releases),
e.g.:

```
pydantic_core-2.49.0-cp314-cp314-android_24_arm64_v8a.whl
```

Then install it:

```bash
pip install pydantic_core-*.whl
```

---

## 🛠️ How it works

All build/release logic lives in a small, independently unit-tested
Python package, [`ci_tool/`](./ci_tool), invoked from thin GitHub Actions
workflows instead of hand-rolled bash `if/elif` chains.

- **Discover.** Query the same APT repository that Termux's `pkg`
  command wraps (`pkg` is a thin convenience layer over `apt`/`dpkg`)
  for the `python` major.minor version it currently serves. This single
  query drives the whole build matrix, rather than a hardcoded version
  list.

- **Fetch the real interpreter library.** Download Termux's actual
  `python` `.deb` for each architecture and extract the real
  `libpython*.so` from it — no mocked/stub library. `pydantic-core`'s
  build script performs a genuine link against it, and a generated
  `_sysconfigdata__android_<triple>.py` feeds `maturin` and
  `pyo3-build-config` consistent ABI/version info.

- **Cross-compile** with `maturin`, using Android NDK r26d (API level
  24) clang wrappers as the linker for each Rust target.

- **Patch + verify.** Set a dual `RPATH` on the compiled extension
  (`$ORIGIN`, plus Termux's real library path) and verify its `NEEDED`
  entries against an allow-list of what bionic + the NDK sysroot
  actually provide — this project's substitute for `auditwheel`, which
  has no Android policy.

- **Retag** the wheel with the correct
  [PEP 738](https://peps.python.org/pep-0738/) Android platform tag,
  e.g. `android_24_arm64_v8a`.

- **Smoke-test** every wheel inside the real, official
  [`termux/termux-docker`](https://github.com/termux/termux-docker)
  image — not a hand-assembled bionic rootfs — installing the exact
  Termux `python` package version used at build time and importing
  `pydantic_core` for real.

- **Publish** wheels to GitHub Releases, with build provenance
  (NDK/maturin/Termux `python` versions) in the release notes, and
  regenerate a [PEP 503](https://peps.python.org/pep-0503/) static
  index published via GitHub Pages.

Builds are triggered by publishing a GitHub Release of this repo, or
manually via `workflow_dispatch` against any `pydantic-core` git ref.

## 🧩 Other Android Python runtimes

This repo officially only tests against Termux. The RPATH set on every
wheel also includes `$ORIGIN` (the directory the extension itself lives
in), which is the layout used by runtimes like
[python-for-android](https://github.com/kivy/python-for-android)/Kivy,
[Flet](https://flet.dev/) and [Chaquopy](https://chaquo.com/chaquopy/) —
so these wheels are *expected* to work there too, for a matching Python
version, but this is not CI-verified.

If you maintain one of these runtimes (or another) and actually depend
on these wheels, please
[open an issue](https://github.com/Eutalix/android-pydantic-core/issues) —
that's what would justify investing in a wider Python version matrix or
a dedicated CI job for your runtime. Without that signal, the single
rolling Termux version is intentionally kept as the only supported
target, to keep the pipeline simple and fully testable.

## 🤝 Credits

- [pydantic-core](https://github.com/pydantic/pydantic-core)

- [termux-docker](https://github.com/termux/termux-docker)

License: MIT
