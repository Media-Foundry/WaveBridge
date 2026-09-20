// Standalone extraction of llama.cpp RMSNorm at fixed revision; see ../README.md.
#include <hip/hip_runtime.h>
#include <hip/math_functions.h>
#if defined(__HIP_PLATFORM_AMD__)
// This standalone SDK view does not force-include Clang's HIP math wrapper.
// Clang's rsqrtf wrapper delegates to this same OCML entry point.
#define rsqrtf __ocml_rsqrt_f32
#endif

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
    value += __shfl_xor(value, offset, kLogicalWidth);
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

static bool hip_ok(hipError_t error, const char *operation) {
  if (error == hipSuccess)
    return true;
  std::fprintf(stderr, "%s: %s\n", operation, hipGetErrorString(error));
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
  hipDeviceProp_t properties{};
  if (!hip_ok(hipGetDeviceProperties(&properties, 0), "hipGetDeviceProperties"))
    return 4;
  char pci_bus_id[64] = {};
  int runtime_version = 0, driver_version = 0;
  if (!hip_ok(hipDeviceGetPCIBusId(pci_bus_id, sizeof(pci_bus_id), 0),
              "hipDeviceGetPCIBusId") ||
      !hip_ok(hipRuntimeGetVersion(&runtime_version), "hipRuntimeGetVersion") ||
      !hip_ok(hipDriverGetVersion(&driver_version), "hipDriverGetVersion"))
    return 4;
  std::printf("device_name=%s\ngcn_arch_name=%s\npci_bus_id=%s\n"
              "hip_runtime_version=%d\nhip_driver_version=%d\n"
              "host_reported_warp_size=%d\nlogical_width=%d\n",
              properties.name, properties.gcnArchName, pci_bus_id, runtime_version,
              driver_version, properties.warpSize, kLogicalWidth);
  float *device_input = nullptr, *device_output = nullptr;
  const std::size_t bytes = count * sizeof(float);
  if (!hip_ok(hipMalloc(&device_input, bytes), "hipMalloc(input)") ||
      !hip_ok(hipMalloc(&device_output, bytes), "hipMalloc(output)") ||
      !hip_ok(hipMemcpy(device_input, input.data(), bytes, hipMemcpyHostToDevice),
              "hipMemcpy(input)"))
    return 4;
  hipLaunchKernelGGL(rms_norm_f32_logical32, dim3(nrows), dim3(kBlockSize),
                     32 * sizeof(float), 0, device_input, device_output, ncols,
                     1.0e-5f);
  if (!hip_ok(hipGetLastError(), "kernel launch") ||
      !hip_ok(hipDeviceSynchronize(), "kernel synchronize") ||
      !hip_ok(hipMemcpy(output.data(), device_output, bytes,
                       hipMemcpyDeviceToHost), "hipMemcpy(output)"))
    return 5;
  (void)hipFree(device_input);
  (void)hipFree(device_output);
  std::ofstream destination(argv[2], std::ios::binary);
  destination.write(reinterpret_cast<const char *>(output.data()), bytes);
  if (!destination)
    return 6;
  std::printf("nrows=%d\nncols=%d\nblock=256\ndynamic_shared_bytes=128\n", nrows,
              ncols);
  return 0;
}
