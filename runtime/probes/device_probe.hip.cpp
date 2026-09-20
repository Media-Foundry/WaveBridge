#include <hip/hip_runtime.h>

#include <cstdint>
#include <cstdio>
#include <vector>

__global__ void wavebridge_probe(int *wave_sizes, unsigned long long *ballots,
                                 int *shuffles) {
  const int lane = static_cast<int>(threadIdx.x);
  wave_sizes[lane] = warpSize;
  ballots[lane] = __ballot(1);
  shuffles[lane] = __shfl(lane, warpSize - 1, warpSize);
}

static void print_ints(const char *key, const std::vector<int> &values) {
  std::printf("%s=", key);
  for (std::size_t i = 0; i < values.size(); ++i)
    std::printf("%s%d", i ? "," : "", values[i]);
  std::printf("\n");
}

static void print_u64s(const char *key,
                       const std::vector<unsigned long long> &values) {
  std::printf("%s=", key);
  for (std::size_t i = 0; i < values.size(); ++i)
    std::printf("%s%016llx", i ? "," : "", values[i]);
  std::printf("\n");
}

int main() {
  int count = 0;
  hipError_t error = hipGetDeviceCount(&count);
  if (error != hipSuccess) {
    std::printf("failure_kind=%s\n",
                error == hipErrorNoDevice ? "no_device" : "runtime_error");
    std::fprintf(stderr, "hipGetDeviceCount: %s\n", hipGetErrorString(error));
    return 4;
  }
  std::printf("device_count=%d\n", count);
  if (count < 1) {
    std::printf("failure_kind=no_device\n");
    std::fprintf(stderr, "no HIP device is visible\n");
    return 4;
  }
  int runtime_version = 0, driver_version = 0;
  if (hipRuntimeGetVersion(&runtime_version) != hipSuccess ||
      hipDriverGetVersion(&driver_version) != hipSuccess) {
    std::printf("failure_kind=runtime_error\n");
    std::fprintf(stderr, "could not query HIP runtime/driver versions\n");
    return 5;
  }
  std::printf("hip_runtime_version=%d\n", runtime_version);
  std::printf("hip_driver_version=%d\n", driver_version);

  hipDeviceProp_t prop{};
  if ((error = hipGetDeviceProperties(&prop, 0)) != hipSuccess) {
    std::printf("failure_kind=runtime_error\n");
    std::fprintf(stderr, "hipGetDeviceProperties: %s\n",
                 hipGetErrorString(error));
    return 5;
  }
  char pci[64] = {};
  if (hipDeviceGetPCIBusId(pci, sizeof(pci), 0) != hipSuccess)
    std::snprintf(pci, sizeof(pci), "unavailable");
  std::printf("device_name=%s\n", prop.name);
  std::printf("gcn_arch_name=%s\n", prop.gcnArchName);
  std::printf("pci_bus_id=%s\n", pci);
  std::printf("host_reported_warp_size=%d\n", prop.warpSize);

  constexpr int threads = 64;
  int *d_wave = nullptr, *d_shuffle = nullptr;
  unsigned long long *d_ballot = nullptr;
  if (hipMalloc(&d_wave, threads * sizeof(int)) != hipSuccess ||
      hipMalloc(&d_ballot, threads * sizeof(unsigned long long)) != hipSuccess ||
      hipMalloc(&d_shuffle, threads * sizeof(int)) != hipSuccess) {
    std::printf("failure_kind=runtime_error\n");
    std::fprintf(stderr, "device allocation failed\n");
    return 6;
  }
  hipLaunchKernelGGL(wavebridge_probe, dim3(1), dim3(threads), 0, 0, d_wave,
                     d_ballot, d_shuffle);
  if ((error = hipDeviceSynchronize()) != hipSuccess) {
    std::printf("failure_kind=runtime_error\n");
    std::fprintf(stderr, "kernel execution: %s\n", hipGetErrorString(error));
    return 7;
  }
  std::vector<int> wave(threads), shuffle(threads);
  std::vector<unsigned long long> ballot(threads);
  if (hipMemcpy(wave.data(), d_wave, threads * sizeof(int),
                hipMemcpyDeviceToHost) != hipSuccess ||
      hipMemcpy(ballot.data(), d_ballot,
                threads * sizeof(unsigned long long),
                hipMemcpyDeviceToHost) != hipSuccess ||
      hipMemcpy(shuffle.data(), d_shuffle, threads * sizeof(int),
      hipMemcpyDeviceToHost) != hipSuccess) {
    std::printf("failure_kind=runtime_error\n");
    std::fprintf(stderr, "device copy failed\n");
    return 8;
  }
  (void)hipFree(d_wave);
  (void)hipFree(d_ballot);
  (void)hipFree(d_shuffle);
  print_ints("device_warp_sizes", wave);
  print_u64s("ballots", ballot);
  print_ints("shuffles", shuffle);
  return 0;
}
