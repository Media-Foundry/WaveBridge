#!/usr/bin/env python3
"""Create a project-local linker view of one existing ROCm SDK core wheel.

This does not install, upgrade, or modify the SDK. It supplies the unversioned
HIP link name from that same SDK's versioned runtime, recording all inputs.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import tempfile


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(sdk_root: Path, output_base: Path, arch: str) -> Path:
    sdk = sdk_root.resolve(strict=True)
    if not re.fullmatch(r"gfx[0-9a-f]+", arch):
        raise ValueError("expected an explicit AMDGPU architecture, e.g. gfx1100")
    compiler = sdk / "lib/llvm/bin/clang++"
    header = sdk / "include/hip/hip_version.h"
    device_lib = sdk / "lib/llvm/amdgcn/bitcode/ocml.bc"
    for path in (compiler, header, device_lib):
        if not path.is_file():
            raise ValueError(f"incomplete SDK: {path}")
    major_match = re.search(r"^#define HIP_VERSION_MAJOR\s+(\d+)\s*$",
                            header.read_text(), re.MULTILINE)
    if major_match is None:
        raise ValueError("cannot establish HIP header major version")
    runtime = sdk / f"lib/libamdhip64.so.{major_match.group(1)}"
    if not runtime.is_file():
        raise ValueError(f"matching versioned runtime missing: {runtime}")
    output_base = output_base.resolve()
    output_base.mkdir(parents=True, exist_ok=True)
    view = Path(tempfile.mkdtemp(prefix="sdk-view-", dir=output_base))
    (view / "include").symlink_to(sdk / "include", target_is_directory=True)
    (view / "lib").mkdir()
    (view / "bin").mkdir()
    for entry in (sdk / "lib").iterdir():
        (view / "lib" / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
    link = view / "lib/libamdhip64.so"
    if not link.exists() and not link.is_symlink():
        link.symlink_to(runtime)
    if not link.is_file():
        raise ValueError("SDK has an unusable unversioned HIP runtime link")
    if not link.samefile(runtime):
        raise ValueError("unversioned HIP runtime does not name the matched versioned library")
    command = [str(compiler), "-x", "hip", "--hip-link", f"--offload-arch={arch}",
               f"--rocm-path={sdk}", f"--hip-path={view}",
               f"--rocm-device-lib-path={device_lib.parent}",
               f"-Wl,-rpath,{sdk / 'lib'}"]
    wrapper = view / "bin/hipcc"
    wrapper.write_text("#!/bin/sh\nexec " + shlex.join(command) + ' "$@"\n')
    wrapper.chmod(0o755)
    metadata = {
        "schema_version": "wavebridge-sdk-view/v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sdk_root": str(sdk), "view": str(view), "architecture": arch,
        "compiler_command_prefix": command,
        "inputs": [{"path": str(p), "sha256": fingerprint(p)}
                   for p in (compiler, header, runtime, device_lib)],
        "wrapper": {"path": str(wrapper), "sha256": fingerprint(wrapper)},
        "sdk_modified": False,
        "scope": "linker_alias_view_not_a_complete_development_package_or_device_validation",
    }
    (view / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return wrapper


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--output-base", type=Path, default=Path("artifacts/toolchains"))
    parser.add_argument("--arch", required=True)
    args = parser.parse_args()
    print(prepare(args.sdk_root, args.output_base, args.arch))


if __name__ == "__main__":
    main()
