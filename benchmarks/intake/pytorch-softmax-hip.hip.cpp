// Hand-integrated pilot. Generated header differs only at listed dependency/trace sites.
#include "wavebridge_softmax_compat.h"
#include <dlfcn.h>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>
#include <vector>
#include "PersistentSoftmax.hip.cuh"

__global__ void wb_width_probe(int* output) { output[0] = warpSize; }

int main(int argc, char** argv) {
    if (argc != 4) return 3;
    const int rows = std::stoi(argv[1]), columns = std::stoi(argv[2]);
    const std::string pattern = argv[3];
    if ((rows != 1 && rows != 3 && rows != 17) || (columns != 65 && columns != 128) ||
        (pattern != "zero" && pattern != "sawtooth" && pattern != "alternating")) return 3;
    wb_hip_check(hipSetDevice(0));
    hipDeviceProp_t properties{};
    wb_hip_check(hipGetDeviceProperties(&properties, 0));
    int runtime_version = 0, driver_version = 0;
    wb_hip_check(hipRuntimeGetVersion(&runtime_version));
    wb_hip_check(hipDriverGetVersion(&driver_version));
    Dl_info api_library{};
    if (!dladdr(reinterpret_cast<void*>(&hipGetDeviceProperties), &api_library) || !api_library.dli_fname) return 8;
    // This first pilot is explicitly restricted to W7900/gfx1100 wave32.
    if (std::string(properties.gcnArchName).find("gfx1100") != 0 || properties.warpSize != 32 ||
        (std::string(properties.name) != "AMD Radeon Pro W7900" &&
         std::string(properties.name) != "AMD Radeon Pro W7900 Dual Slot")) return 4;
    const size_t count = size_t(rows) * columns;
    // Inactive tail groups still form pointers before checking local_batches.
    // Keep those pointers within allocated storage, without adding logical rows.
    const int padded_rows = ((rows + 7) / 8) * 8;
    const size_t allocated_count = size_t(padded_rows) * columns;
    std::vector<float> input(allocated_count), output(allocated_count);
    for (size_t i = 0; i < count; ++i) {
        if (pattern == "sawtooth") input[i] = (int((i * 17) % 101) - 50) / 8.0f;
        else if (pattern == "alternating") input[i] = (i % 2 == 0) ? 8.0f : -8.0f;
    }
    float *device_input = nullptr, *device_output = nullptr;
    bool* device_mask = nullptr;
    int* device_width = nullptr;
    wb_hip_check(hipMalloc(&device_input, allocated_count * sizeof(float)));
    wb_hip_check(hipMalloc(&device_output, allocated_count * sizeof(float)));
    wb_hip_check(hipMalloc(&device_mask, allocated_count * sizeof(bool)));
    wb_hip_check(hipMalloc(&device_width, sizeof(int)));
    wb_hip_check(hipMemcpy(device_input, input.data(), allocated_count * sizeof(float), hipMemcpyHostToDevice));
    constexpr uint32_t padding_sentinel = 0x7fc12345;
    std::vector<uint32_t> sentinel_storage(allocated_count, padding_sentinel);
    wb_hip_check(hipMemcpy(device_output, sentinel_storage.data(), allocated_count * sizeof(float), hipMemcpyHostToDevice));
    wb_hip_check(hipMemset(device_mask, 0, allocated_count * sizeof(bool)));
    wb_width_probe<<<1, 1>>>(device_width);
    wb_hip_check(hipGetLastError());
    int observed_width = 0;
    wb_hip_check(hipMemcpy(&observed_width, device_width, sizeof(int), hipMemcpyDeviceToHost));
    if (observed_width != properties.warpSize) return 5;
    dispatch_softmax_forward<float, float, float, false, false>(
        device_output, device_input, columns, columns, rows, device_mask);
    wb_hip_check(hipDeviceSynchronize());
    wb_hip_check(hipMemcpy(output.data(), device_output, allocated_count * sizeof(float), hipMemcpyDeviceToHost));
    if (wb_api_calls != 1 || wb_api_device != 0 || wb_api_width != observed_width || wb_launch_count != 1) return 6;
    for (size_t i = 0; i < count; ++i) if (!std::isfinite(output[i])) return 7;
    for (size_t i = count; i < allocated_count; ++i) {
        uint32_t bits = 0;
        std::memcpy(&bits, &output[i], sizeof(bits));
        if (bits != padding_sentinel) return 9;
    }
    std::cout << std::setprecision(9) << "{\"rows\":" << rows << ",\"columns\":" << columns
              << ",\"device_name\":" << std::quoted(properties.name)
              << ",\"architecture\":" << std::quoted(properties.gcnArchName)
              << ",\"padded_rows\":" << padded_rows << ",\"padding_sentinel_preserved\":true"
              << ",\"hip_api_library\":" << std::quoted(api_library.dli_fname)
              << ",\"hip_runtime_version\":" << runtime_version << ",\"hip_driver_version\":" << driver_version
              << ",\"pci_domain\":" << properties.pciDomainID
              << ",\"pci_bus\":" << properties.pciBusID << ",\"pci_device\":" << properties.pciDeviceID
              << ",\"api_width\":" << wb_api_width << ",\"device_width\":" << observed_width
              << ",\"api_calls\":" << wb_api_calls << ",\"softmax_dispatch_launch_count\":" << wb_launch_count
              << ",\"grid\":" << wb_grid << ",\"block\":[" << wb_threads.x << ',' << wb_threads.y << ',' << wb_threads.z
              << "],\"output\":[";
    for (size_t i = 0; i < count; ++i) std::cout << (i ? "," : "") << output[i];
    std::cout << "]}\n";
    wb_hip_check(hipFree(device_input)); wb_hip_check(hipFree(device_output));
    wb_hip_check(hipFree(device_mask)); wb_hip_check(hipFree(device_width));
}
