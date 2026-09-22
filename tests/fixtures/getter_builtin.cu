// Frontend-only fixture: no CUDA runtime, GPU execution, or launch assumptions.
extern __attribute__((device)) int sink;
extern __attribute__((device)) void opaque();

__attribute__((device)) unsigned builtin_getter() {
  return __nvvm_read_ptx_sreg_ctaid_x();
}

__attribute__((device)) unsigned builtin_with_store() {
  sink = 1;
  return __nvvm_read_ptx_sreg_ctaid_x();
}

__attribute__((device)) unsigned builtin_with_call() {
  opaque();
  return __nvvm_read_ptx_sreg_ctaid_x();
}
