// Manual framework-free HIP compatibility boundary, not PyTorch runtime linkage.
#pragma once
#include <__clang_hip_runtime_wrapper.h>
#include <hip/hip_runtime.h>
#include <cmath>
#include <cstdio>
#include <cstdlib>

inline void wb_hip_check(hipError_t status) {
    if (status != hipSuccess) {
        std::fprintf(stderr, "HIP failure: %s\n", hipGetErrorString(status));
        std::exit(2);
    }
}
#define TORCH_INTERNAL_ASSERT(condition) do { if (!(condition)) std::abort(); } while (0)
#define C10_CUDA_KERNEL_LAUNCH_CHECK() wb_hip_check(hipGetLastError())
// Explicit manual compile specialization: modern HIP warpSize is not constexpr.
// This is NOT the runtime API result; the harness gates/query-checks that result.
#ifndef WB_COMPILED_COOP_WIDTH
#error "Pass the declared compile-time cooperation width"
#endif
static_assert(WB_COMPILED_COOP_WIDTH == 32, "pilot supports only width32");
#define C10_WARP_SIZE WB_COMPILED_COOP_WIDTH
template <typename T>
__device__ __forceinline__ T WARP_SHFL_XOR(T value, int lane_mask, int width) {
    return __shfl_xor(value, lane_mask, width);
}
inline int wb_api_width = -1, wb_api_device = -1, wb_api_calls = 0;
inline int wb_launch_count = 0, wb_grid = 0;
inline dim3 wb_threads;
namespace at::cuda {
inline int warp_size() {
    hipDeviceProp_t properties{};
    wb_hip_check(hipGetDevice(&wb_api_device));
    wb_hip_check(hipGetDeviceProperties(&properties, wb_api_device));
    wb_api_width = properties.warpSize;
    ++wb_api_calls;
    return wb_api_width;
}
inline hipStream_t getCurrentCUDAStream() { return nullptr; }
}
inline int wb_observe_grid(int blocks, dim3 threads) {
    wb_grid = blocks;
    wb_threads = threads;
    ++wb_launch_count;
    return blocks;
}
