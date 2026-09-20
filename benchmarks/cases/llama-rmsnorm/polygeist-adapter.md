# Polygeist host adapter boundary

`baseline/rmsnorm_logical32_polygeist_adapter.cu` is a manual frontend adapter
derived from the fixed CUDA standalone. It exists because the pinned cgeist
frontend reaches an internal assertion while translating the standalone host
`std::vector` and initializer-list machinery. That tool failure is not evidence
that the RMSNorm kernel semantics are unsupported.

The constants and all three computation functions are copied verbatim from
`baseline/rmsnorm_logical32.cu`. The adapter replaces file I/O, containers,
allocation, copies, device queries, synchronization, and measurement with one
unmangled C entry point. Its domain guard and CUDA launch preserve the original
grid, block, dynamic shared-memory expression, stream, kernel argument order,
and epsilon. `polygeist-adapter.patch` records the complete mechanical boundary.

An external harness remains responsible for allocating device buffers, copying
inputs and outputs, checking launch/runtime errors, synchronizing, recording the
device identity, and applying the frozen numeric protocol. The adapter has not
been executed on a CUDA GPU and has no independent numeric or machine-code
validation. It is not an automatically recovered candidate, a new kernel
lineage, or a semantic-equivalence result.

The pinned cgeist subsequently emitted unverified MLIR for the whole adapter in
both its default O0 pipeline and its `--cuda-lower` pipeline. Local reports are
indexed in `polygeist-adapter.json`. The default output contains the kernel and
both reduction helpers, but the lowered output's shared-memory capacity/indexing
and its external NVVM shuffle declaration have not been semantically validated.
These emissions only establish that the pinned frontend processed this
explicitly bounded source; they do not establish correct lowering, executable
code, or kernel equivalence.
