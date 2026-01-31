# 📱 Android Pydantic Core

[![Build & Release](https://img.shields.io/github/actions/workflow/status/Eutalix/android-pydantic-core/build_wheels?label=Build)](https://github.com/Eutalix/android-pydantic-core/actions)
[![Python Versions](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://github.com/Eutalix/android-pydantic-core/releases)
[![Architectures](https://img.shields.io/badge/arch-arm64%20%7C%20armv7%20%7C%20x86%20%7C%20x86__64-orange)](https://github.com/Eutalix/android-pydantic-core/releases)

**Automated builds of `pydantic-core` optimized for Android (Termux).**

Compiling `pydantic-core` on Android requires a Rust toolchain and takes ~15 minutes (or fails due to memory). This repository provides pre-built wheels that install instantly via `pip`.

## 📦 Supported Targets

| Architecture | Device Type | Status |
|--------------|-------------|--------|
| `aarch64` | Modern Smartphones | ✅ Supported |
| `armv7` | Older Devices | ✅ Supported |
| `x86_64` | Emulators / Chromebooks | ✅ Supported |
| `x86` | Old Emulators | ✅ Supported |

> **Python Versions:** 3.9, 3.10, 3.11, 3.12, 3.13

---

## 🚀 Installation

### ⚡ Option 1: Quick Install (Script)
Use this if you want the installer to **auto-detect** your architecture and Python version.

```bash
curl -sL https://raw.githubusercontent.com/Eutalix/android-pydantic-core/main/install_pydantic_core.sh | bash
```

### 🐍 Option 2: Pip (Standard)
Best for requirements files or CI/CD.

```bash
pip install pydantic-core --extra-index-url https://eutalix.github.io/android-pydantic-core/
```

### 📦 Option 3: Manual Download
You can manually download the `.whl` files from the [Releases Page](https://github.com/Eutalix/android-pydantic-core/releases).

1. Download the file matching your Python version (`cp312`) and Architecture (`aarch64`).
2. Install it:
   ```bash
   pip install pydantic_core-*.whl
   ```

---

## 🛠️ How it works

This repository uses **GitHub Actions** to cross-compile wheels using the Android NDK r25b.

1.  **Checks PyPI** for new versions daily.
2.  **Cross-compiles** using `maturin` and patched linker flags:
    *   **RPATH Fix:** Hardcodes Termux library paths (`/data/data/com.termux/files/usr/lib`) so the linker finds `libpython`.
    *   **Force Needed:** Uses `--no-as-needed` to ensure `libpython` dependencies are correctly recorded.
3.  **Renames** artifacts to `linux_{arch}` for Termux compatibility.
4.  **Publishes** wheels to GitHub Releases and updates the PEP 503 Index.

## 🤝 Credits

- [pydantic](https://github.com/pydantic/pydantic-core)

License: MIT