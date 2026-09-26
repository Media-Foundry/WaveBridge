// Compiler-only probe: never launched on a GPU. This does not test participation,
// valid masks, routing, normal return, or floating-point output correctness.
extern "C" __attribute__((device)) float wb_shuffle_leaf(
    unsigned mask, float value, int lane_mask, int control) {
  return __nvvm_shfl_sync_bfly_f32(mask, value, lane_mask, control);
}
