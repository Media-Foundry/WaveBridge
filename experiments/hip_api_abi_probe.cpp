// Compile-only host ABI observation. No HIP calls or GPU execution.
#include <hip/hip_runtime_api.h>

void WaveBridgeHipAbiProbe() {
  using Underlying = __underlying_type(hipError_t);
  enum Observations {
    int_bits = sizeof(int) * __CHAR_BIT__,
    status_bits = sizeof(hipError_t) * __CHAR_BIT__,
    underlying_bits = sizeof(Underlying) * __CHAR_BIT__,
    underlying_is_unsigned = Underlying(-1) > Underlying(0),
    underlying_is_unsigned_int = __is_same(Underlying, unsigned int),
    success_as_int = static_cast<int>(hipSuccess),
    last_named_status_as_int = static_cast<int>(hipErrorTbd),
    unsigned_max_converts_to_minus_one = static_cast<int>(~0u) == -1,
  };
}
