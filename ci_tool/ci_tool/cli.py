"""Thin CLI gluing every ci_tool module together for one build-matrix
cell. Invoked from the workflow YAML, which stays a dumb wrapper around
tested Python.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from packaging.utils import parse_wheel_filename

from . import smoke_test as smoke_test_mod
from .arches import get
from .build import BuildConfig, retag_wheel, run_maturin_build
from .discover import discover_python_version
from .patch import patch_extension_in_wheel
from .pypi_index import build_index
from .release_notes import ReleaseContext, WheelBuildInfo, render
from .sysconfigdata import write as write_sysconfigdata
from .termux import fetch_libpython_for_arch
from .upstream import UPSTREAM_REPO_DEFAULT, check_for_update, version_from_ref
from .wheel_tags import android_abi_tag


def _discover_python_version(args: argparse.Namespace) -> None:
    arch = get(args.abi)
    version = discover_python_version(arch)
    print(f"python_version={version}")
    if args.github_output:
        with open(args.github_output, "a") as f:
            f.write(f"python_version={version}\n")


def _build(args: argparse.Namespace) -> None:
    arch = get(args.abi)
    cache_dir = Path(args.cache_dir).resolve()
    lib_path, termux_pkg_version = fetch_libpython_for_arch(
        arch, cache_dir, python_version=args.python_version
    )
    sysconfig_dir = lib_path.parent

    write_sysconfigdata(
        sysconfig_dir,
        python_version=args.python_version,
        arch=arch,
        android_api_level=args.android_api_level,
    )

    cfg = BuildConfig(
        arch=arch,
        python_version=args.python_version,
        android_api_level=args.android_api_level,
        ndk_home=Path(args.ndk_home),
        libpython_dir=sysconfig_dir,
        manifest_path=Path(args.manifest_path),
        out_dir=Path(args.out_dir),
    )
    wheel_path = run_maturin_build(cfg)
    patch_extension_in_wheel(wheel_path)
    final_path = retag_wheel(wheel_path, cfg)

    # Sidecar metadata lets later `smoke-test`/`release-notes` invocations
    # (separate jobs, artifacts re-downloaded) reconstruct build info
    # without re-deriving anything from the filename alone.
    meta_path = final_path.with_suffix(".whl.json")
    meta_path.write_text(
        json.dumps(
            {
                "android_abi": arch.android_abi,
                "python_version": args.python_version,
                "wheel_filename": final_path.name,
                "termux_python_pkg_version": termux_pkg_version,
            }
        )
    )

    print(f"wheel={final_path}")
    if args.github_output:
        with open(args.github_output, "a") as f:
            f.write(f"wheel_path={final_path}\n")
            f.write(f"termux_python_pkg_version={termux_pkg_version}\n")


def _smoke_test(args: argparse.Namespace) -> None:
    arch = get(args.abi)
    abi_tag = android_abi_tag(arch)
    wheel_dir = Path(args.wheel_dir)

    candidates = sorted(p for p in wheel_dir.rglob("*.whl") if abi_tag in p.name)
    if not candidates:
        raise RuntimeError(f"No wheels found matching abi tag {abi_tag!r} in {wheel_dir}")

    skipped: list[str] = []
    failed: list[str] = []

    for wheel_path in candidates:
        meta_path = wheel_path.with_suffix(".whl.json")
        if not meta_path.exists():
            raise RuntimeError(
                f"Missing sidecar metadata {meta_path}; was {wheel_path.name} "
                "built via `ci_tool build`?"
            )
        meta = json.loads(meta_path.read_text())
        _name, version, _build_tag, _tags = parse_wheel_filename(wheel_path.name)

        try:
            smoke_test_mod.run_smoke_test(
                arch=arch,
                dist_dir=wheel_path.parent,
                wheel_filename=wheel_path.name,
                termux_python_pkg_version=meta["termux_python_pkg_version"],
                expected_pydantic_core_version=str(version),
            )
            print(f"OK: {wheel_path.name} ({smoke_test_mod.docker_image(arch)})")
        except smoke_test_mod.SmokeTestSkipped as exc:
            print(f"SKIP: {wheel_path.name}: {exc}")
            skipped.append(wheel_path.name)
        except RuntimeError as exc:
            print(str(exc))
            failed.append(wheel_path.name)

    if failed:
        raise RuntimeError(f"Smoke test failed for: {failed} (skipped: {skipped})")
    if skipped:
        print(f"Note: {len(skipped)} wheel(s) skipped due to unavailable Termux python version: {skipped}")


def _release_notes(args: argparse.Namespace) -> None:
    dist_dir = Path(args.dist_dir)
    wheels = []
    for meta_path in sorted(dist_dir.rglob("*.whl.json")):
        data = json.loads(meta_path.read_text())
        wheels.append(WheelBuildInfo(**data))

    ctx = ReleaseContext(
        pydantic_core_version=args.pydantic_core_version,
        ndk_version=args.ndk_version,
        android_api_level=args.android_api_level,
        maturin_version=args.maturin_version,
        wheels=wheels,
    )
    Path(args.output).write_text(render(ctx))


def _generate_index(args: argparse.Namespace) -> None:
    count = build_index(repo=args.repo, package_name=args.package_name, site_dir=Path(args.site_dir))
    print(f"indexed {count} wheel(s) for {args.package_name}")


def _check_upstream(args: argparse.Namespace) -> None:
    result = check_for_update(args.repo, args.package_name, upstream_repo=args.upstream_repo)
    print(f"package_version={result.package_version}")
    print(f"upstream_ref={result.upstream_ref}")
    print(f"should_build={str(result.should_build).lower()}")
    if args.github_output:
        with open(args.github_output, "a") as f:
            f.write(f"should_build={str(result.should_build).lower()}\n")
            f.write(f"package_version={result.package_version}\n")
            f.write(f"release_tag={result.release_tag}\n")
            f.write(f"upstream_ref={result.upstream_ref}\n")


def _resolve_ref(args: argparse.Namespace) -> None:
    version = version_from_ref(args.ref) or ""
    print(f"release_version={version}")
    if args.github_output:
        with open(args.github_output, "a") as f:
            f.write(f"release_version={version}\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ci_tool")
    sub = parser.add_subparsers(dest="command", required=True)

    dp_p = sub.add_parser(
        "discover-python-version",
        help="Query Termux's apt pool for the python major.minor version it currently serves",
    )
    dp_p.add_argument("--abi", required=True)
    dp_p.add_argument("--github-output", default=None)
    dp_p.set_defaults(func=_discover_python_version)

    build_p = sub.add_parser("build", help="Build one wheel for one (abi, python) cell")
    build_p.add_argument("--abi", required=True)
    build_p.add_argument("--python-version", required=True)
    build_p.add_argument("--android-api-level", type=int, default=24)
    build_p.add_argument("--ndk-home", required=True)
    build_p.add_argument("--manifest-path", required=True)
    build_p.add_argument("--out-dir", required=True)
    build_p.add_argument("--cache-dir", default=".ci-cache")
    build_p.add_argument("--github-output", default=None)
    build_p.set_defaults(func=_build)

    st_p = sub.add_parser("smoke-test", help="Run built wheels against the real termux-docker image")
    st_p.add_argument("--abi", required=True)
    st_p.add_argument("--wheel-dir", required=True)
    st_p.set_defaults(func=_smoke_test)

    rn_p = sub.add_parser("release-notes", help="Render release notes from built wheel metadata")
    rn_p.add_argument("--dist-dir", required=True)
    rn_p.add_argument("--pydantic-core-version", required=True)
    rn_p.add_argument("--ndk-version", required=True)
    rn_p.add_argument("--android-api-level", type=int, default=24)
    rn_p.add_argument("--maturin-version", required=True)
    rn_p.add_argument("--output", required=True)
    rn_p.set_defaults(func=_release_notes)

    idx_p = sub.add_parser("generate-index", help="Generate a PEP 503 static index from GitHub Releases")
    idx_p.add_argument("--repo", required=True)
    idx_p.add_argument("--package-name", default="pydantic-core")
    idx_p.add_argument("--site-dir", default="site")
    idx_p.set_defaults(func=_generate_index)

    cu_p = sub.add_parser(
        "check-upstream",
        help="Check PyPI for a pydantic-core version not yet released by this repo",
    )
    cu_p.add_argument("--repo", required=True)
    cu_p.add_argument("--package-name", default="pydantic-core")
    cu_p.add_argument("--upstream-repo", default=UPSTREAM_REPO_DEFAULT)
    cu_p.add_argument("--github-output", default=None)
    cu_p.set_defaults(func=_check_upstream)

    rr_p = sub.add_parser(
        "resolve-ref",
        help="Derive a release version from a git ref, if it looks like one",
    )
    rr_p.add_argument("--ref", required=True)
    rr_p.add_argument("--github-output", default=None)
    rr_p.set_defaults(func=_resolve_ref)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
