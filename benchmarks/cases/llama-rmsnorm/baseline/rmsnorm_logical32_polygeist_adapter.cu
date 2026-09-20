// Manual host adapter for frontend comparison; see ../polygeist-adapter.md.
#include <cuda_runtime.h>

#include <cstdint>

constexpr int kLogicalWidth = 32;
constexpr int kBlockSize = 256;

static __device__ __forceinline__ float warp_reduce_sum_logical32(float value) {
#pragma unroll
  for (int offset = kLogicalWidth / 2; offset > 0; offset >>= 1)
    value += __shfl_xor_sync(0xffffffffu, value, offset, kLogicalWidth);
  return value;
}

static __device__ float block_reduce_sum_logical32(float value,
                                                    float *shared_values) {
  value = warp_reduce_sum_logical32(value);
  const int logical_group = threadIdx.x / kLogicalWidth;
  const int logical_lane = threadIdx.x % kLogicalWidth;
  if (logical_lane == 0)
    shared_values[logical_group] = value;
  __syncthreads();
  value = logical_lane < (kBlockSize / kLogicalWidth)
              ? shared_values[logical_lane]
              : 0.0f;
  return warp_reduce_sum_logical32(value);
}

__global__ void rms_norm_f32_logical32(const float *x, float *dst,
                                       int ncols, float epsilon) {
  const int row = blockIdx.x;
  const int tid = threadIdx.x;
  x += static_cast<int64_t>(row) * ncols;
  dst += static_cast<int64_t>(row) * ncols;
  float partial = 0.0f;
  for (int col = tid; col < ncols; col += kBlockSize) {
    const float value = x[col];
    partial += value * value;
  }
  extern __shared__ float shared_sum[];
  const float total = block_reduce_sum_logical32(partial, shared_sum);
  const float scale = rsqrtf(total / ncols + epsilon);
  for (int col = tid; col < ncols; col += kBlockSize)
    dst[col] = scale * x[col];
}

extern "C" int wavebridge_launch_rms_norm_f32_logical32(
    const float *device_input, float *device_output, int nrows, int ncols) {
  if (nrows < 1 || nrows > 8 || ncols < 1 || ncols >= 1024)
    return 3;
  rms_norm_f32_logical32<<<dim3(nrows), dim3(kBlockSize), 32 * sizeof(float), 0>>>(
      device_input, device_output, ncols, 1.0e-5f);
  return 0;
}
