# 📱 Android Pydantic Core

[![Build Status](https://img.shields.io/github/actions/workflow/status/Eutalix/android-pydantic-core/build_wheels.yml?label=Build)](https://github.com/Eutalix/android-pydantic-core/actions)
[![Python Versions](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://github.com/Eutalix/android-pydantic-core/tree/main/python)
[![Architectures](https://img.shields.io/badge/arch-arm64%20%7C%20armv7%20%7C%20x86%20%7C%20x86__64-orange)]()

**Automated daily builds of `pydantic-core` optimized for Android (Termux).**

Compiling `pydantic-core` on Android requires a Rust toolchain and takes ~15 minutes. This repository provides pre-built wheels that install instantly via `pip`.

## 📦 Supported Targets

| Architecture | Device Type | Status |
|--------------|-------------|--------|
| `aarch64` | Modern Smartphones | ✅ Supported |
| `armv7` | Older Devices | ✅ Supported |
| `x86_64` | Emulators / Chromebooks | ✅ Supported |
| `x86` | Old Emulators | ✅ Supported |

> **Python Versions:** 3.9, 3.10, 3.11, 3.12, 3.13

## 🚀 Usage

You can install these wheels directly via URL or browse the repository structure.

**Raw URL Pattern:**
```
https://raw.githubusercontent.com/Eutalix/android-pydantic-core/main/python/{py_ver}/pydantic-core/{ver}/{filename}.whl
```

**Example (Python 3.12 on ARM64):**
```bash
pip install https://raw.githubusercontent.com/Eutalix/android-pydantic-core/main/python/3.12/pydantic-core/2.41.5/pydantic_core-2.41.5-cp312-cp312-linux_aarch64.whl
```

## 🛠️ How it works

This repository uses **GitHub Actions** to cross-compile wheels using the Android NDK r25b.
1.  Checks PyPI for new versions daily.
2.  Builds wheels for all architectures using `maturin`.
3.  Renames artifacts to `linux_{arch}` to ensure compatibility with Termux `pip`.
4.  Commits the binaries to this repository automatically.

## 🤝 Credits

- [pydantic](https://github.com/pydantic/pydantic-core)

License: MIT