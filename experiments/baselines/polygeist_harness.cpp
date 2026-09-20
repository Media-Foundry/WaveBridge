// External harness for manually adapted Polygeist RMSNorm; not an auto candidate.
// Uses the existing input/output format and frozen numerical reference externally.
#include <hip/hip_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <vector>

constexpr int kLogicalWidth = 32;
extern "C" int wavebridge_launch_rms_norm_f32_logical32(
    const float *, float *, int, int);

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
  if (wavebridge_launch_rms_norm_f32_logical32(
          device_input, device_output, nrows, ncols) != 0)
    return 5;
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
  std::printf("nrows=%d\nncols=%d\nblock=256\nlaunch_resource_metadata=external_artifact_required\n", nrows,
              ncols);
  return 0;
}
