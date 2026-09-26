// Compile-only observations. This is a synthetic probe, not a production kernel.
#include <limits>

extern "C" {
__device__ __attribute__((noinline, used)) float wb_huge() {
  return __builtin_huge_valf();
}
__device__ __attribute__((noinline, used)) float wb_nan() {
  return __builtin_nanf("");
}
__device__ __attribute__((noinline, used)) float wb_limits_huge() {
  return std::numeric_limits<float>::infinity();
}
__device__ __attribute__((noinline, used)) float wb_limits_nan() {
  return std::numeric_limits<float>::quiet_NaN();
}
__device__ float wb_unimplemented_leaf();
__device__ __attribute__((noinline, used)) float wb_external_control() {
  return wb_unimplemented_leaf();
}
__device__ __attribute__((noinline, used)) float wb_store_control(float* output) {
  *output = 1.0f;
  return __builtin_huge_valf();
}
}
