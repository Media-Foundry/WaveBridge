// Manual HIP-to-CUDA API port of the fixed standalone extraction; see ../cuda-port.md.
#include <cuda_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <vector>

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

static bool cuda_ok(cudaError_t error, const char *operation) {
  if (error == cudaSuccess)
    return true;
  std::fprintf(stderr, "%s: %s\n", operation, cudaGetErrorString(error));
  return false;
}

int main(int argc, char **argv) {
  if (argc != 5) {
    std::fprintf(stderr, "usage: %s INPUT OUTPUT NROWS NCOLS\n", argv[0]);
    return 3;
  }
  const int nrows = std::atoi(argv[3]);
  const int ncols = std::atoi(argv[4]);
  if (nrows < 1 || nrows > 8 || ncols < 1 || ncols >= 1024)
    return 3;
  const std::size_t count = static_cast<std::size_t>(nrows) * ncols;
  std::vector<float> input(count), output(count);
  std::ifstream source(argv[1], std::ios::binary);
  source.read(reinterpret_cast<char *>(input.data()), count * sizeof(float));
  if (!source || source.peek() != std::ifstream::traits_type::eof()) {
    std::fprintf(stderr, "input size mismatch\n");
    return 3;
  }
  cudaDeviceProp properties{};
  if (!cuda_ok(cudaGetDeviceProperties(&properties, 0), "cudaGetDeviceProperties"))
    return 4;
  char pci_bus_id[64] = {};
  int runtime_version = 0, driver_version = 0;
  if (!cuda_ok(cudaDeviceGetPCIBusId(pci_bus_id, sizeof(pci_bus_id), 0),
               "cudaDeviceGetPCIBusId") ||
      !cuda_ok(cudaRuntimeGetVersion(&runtime_version), "cudaRuntimeGetVersion") ||
      !cuda_ok(cudaDriverGetVersion(&driver_version), "cudaDriverGetVersion"))
    return 4;
  std::printf("device_name=%s\npci_bus_id=%s\n"
              "cuda_runtime_version=%d\ncuda_driver_version=%d\n"
              "host_reported_warp_size=%d\nlogical_width=%d\n",
              properties.name, pci_bus_id, runtime_version, driver_version,
              properties.warpSize, kLogicalWidth);
  float *device_input = nullptr, *device_output = nullptr;
  const std::size_t bytes = count * sizeof(float);
  if (!cuda_ok(cudaMalloc(reinterpret_cast<void **>(&device_input), bytes),
               "cudaMalloc(input)") ||
      !cuda_ok(cudaMalloc(reinterpret_cast<void **>(&device_output), bytes),
               "cudaMalloc(output)") ||
      !cuda_ok(cudaMemcpy(device_input, input.data(), bytes, cudaMemcpyHostToDevice),
               "cudaMemcpy(input)"))
    return 4;
  rms_norm_f32_logical32<<<dim3(nrows), dim3(kBlockSize), 32 * sizeof(float), 0>>>(
      device_input, device_output, ncols, 1.0e-5f);
  if (!cuda_ok(cudaGetLastError(), "kernel launch") ||
      !cuda_ok(cudaDeviceSynchronize(), "kernel synchronize") ||
      !cuda_ok(cudaMemcpy(output.data(), device_output, bytes,
                          cudaMemcpyDeviceToHost), "cudaMemcpy(output)"))
    return 5;
  (void)cudaFree(device_input);
  (void)cudaFree(device_output);
  std::ofstream destination(argv[2], std::ios::binary);
  destination.write(reinterpret_cast<const char *>(output.data()), bytes);
  if (!destination)
    return 6;
  std::printf("nrows=%d\nncols=%d\nblock=256\ndynamic_shared_bytes=128\n", nrows,
              ncols);
  return 0;
}
