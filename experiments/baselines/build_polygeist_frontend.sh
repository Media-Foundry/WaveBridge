#!/usr/bin/env bash
# Build the pinned CGO24 frontend only; this does not validate GPU retargeting.
set -euo pipefail
if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: bash $0 POLYGEIST_SOURCE NEW_BUILD_DIR [JOBS=8]" >&2
  exit 2
fi
source_dir=$(realpath "$1")
build_dir=$(realpath -m "$2")
build_jobs=${3:-8}
if [[ ! $build_jobs =~ ^([1-9]|1[0-6])$ ]]; then
  echo "JOBS must be an integer from 1 to 16" >&2
  exit 2
fi
if [[ -e $build_dir ]]; then
  echo "Refusing to overwrite an existing build/evidence directory" >&2
  exit 2
fi
if [[ $build_dir == "$source_dir" || $build_dir == "$source_dir/"* ]]; then
  echo "Build/evidence directory must be outside the source checkout" >&2
  exit 2
fi
polygeist_revision=ba9953a08c9bc0965090911b67b2b1e1778cbb59
llvm_revision=0b9310c6e4416ee48c07edfef81144e22850dfe7
[[ $(git -C "$source_dir" rev-parse HEAD) == "$polygeist_revision" ]]
[[ -f $source_dir/llvm-project/llvm/CMakeLists.txt ]]
[[ $(git -C "$source_dir/llvm-project" rev-parse HEAD) == "$llvm_revision" ]]
[[ -z $(git -C "$source_dir" status --porcelain --untracked-files=normal) ]]
[[ -z $(git -C "$source_dir/llvm-project" status --porcelain --untracked-files=normal) ]]
cc_path=$(command -v clang)
cxx_path=$(command -v clang++)
linker_path=$(command -v ld.lld)
cmake_path=$(command -v cmake)
ninja_path=$(command -v ninja)
mkdir -p "$(dirname "$build_dir")"
mkdir "$build_dir"
{
  date -u +%FT%TZ
  echo "polygeist=$polygeist_revision"
  echo "llvm=$llvm_revision"
  echo "scope=frontend_only_no_gpu_backend_or_execution"
  "$cc_path" --version
  cmake --version
  ninja --version
  "$linker_path" --version
  sha256sum "$(realpath "$cc_path")" "$(realpath "$cxx_path")" \
    "$(realpath "$cmake_path")" "$(realpath "$ninja_path")" \
    "$(realpath "$linker_path")" "$0"
} | tee "$build_dir/environment.log"
(
  set -x
  cmake -G Ninja -S "$source_dir/llvm-project/llvm" -B "$build_dir" \
    -DCMAKE_C_COMPILER="$cc_path" -DCMAKE_CXX_COMPILER="$cxx_path" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DLLVM_ENABLE_PROJECTS='clang;mlir' \
    -DLLVM_EXTERNAL_PROJECTS=polygeist \
    -DLLVM_EXTERNAL_POLYGEIST_SOURCE_DIR="$source_dir" \
    -DLLVM_TARGETS_TO_BUILD=host -DLLVM_ENABLE_ASSERTIONS=ON \
    -DLLVM_USE_LINKER=lld -DLLVM_PARALLEL_LINK_JOBS=1 \
    -DLLVM_INCLUDE_BENCHMARKS=OFF \
    -DPOLYGEIST_ENABLE_CUDA=OFF -DPOLYGEIST_ENABLE_ROCM=OFF \
    -DMLIR_ENABLE_CUDA_RUNNER=OFF -DMLIR_ENABLE_ROCM_RUNNER=OFF
) 2>&1 | tee "$build_dir/configure.log"
(
  set -x
  cmake --build "$build_dir" --target cgeist --parallel "$build_jobs"
) 2>&1 | tee "$build_dir/build.log"
sha256sum "$build_dir/bin/cgeist" | tee "$build_dir/cgeist.sha256"
