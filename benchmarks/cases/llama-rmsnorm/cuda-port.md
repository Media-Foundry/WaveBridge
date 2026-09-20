# CUDA baseline port boundary

`baseline/rmsnorm_logical32.cu` is a manual API port of the fixed HIP standalone
baseline. It is not an automatically recovered candidate and, at the time of
this record, has not been executed on a CUDA GPU.

The reduction, shared-memory staging, barrier, broadcast, 256-thread block,
logical width 32, column loops, launch shape, dynamic shared-memory size, input
domain, and numeric comparison protocol remain intentionally unchanged.

The subgroup intrinsic is the one semantic-sensitive source edit:
`__shfl_xor(value, offset, 32)` becomes
`__shfl_xor_sync(0xffffffffu, value, offset, 32)`. Correct use of the full mask
requires all 32 logical lanes to be active and converged at every call. This is
an explicit external assumption, not a result established by the source port.
Host and device syntax-only checks passed with AOCC Clang 17.0.6 and real CUDA
headers, targeting sm_70. The compiler warns that CUDA 12.1 is only partially
supported. See `cuda-syntax-evidence.json` for successful and failed local report
hashes. Code generation, linking, runtime, device identity, machine-code warp
metadata, and numeric behavior remain unvalidated. Filtered kernel AST collection
does not establish communication semantics or a complete declaration closure.

The upstream source snapshots and MIT license already vendored in this case
remain the provenance and license basis; see `provenance.json` and
`LICENSE.upstream`.
