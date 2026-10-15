// Synthetic CUDA frontend fixture.  It is not a GPU workload or runtime model.
#include "field_snapshot_launch.cu"

#define FIXED_LOAD_KERNEL(NAME, WIDTH, INDEX, BEFORE) \
__attribute__((global)) void NAME(float* output, const float* input, int n, int stride, int rows, int first) { \
    int local_coordinate_y = local_y(); \
    int lane = local_x(); \
    int first_batch = first; \
    int offset = first_batch * stride + lane; \
    input += offset; \
    BEFORE \
    const int batches = 2; \
    const int iterations = 4; \
    float elements[2][4]; \
    for (int row = 0; row < batches; ++row) { \
        int count = row >= rows ? 0 : n; \
        for (int it = 0; it < iterations; ++it) { \
            int column = lane + it * WIDTH; \
            if (column < count) { elements[row][it] = input[INDEX]; } \
            else { elements[row][it] = 0.0f; } \
        } \
    } \
    for (int row = 0; row < batches; ++row) \
        for (int it = 0; it < iterations; ++it) \
            output[row * 128 + lane + it * 32] = elements[row][it]; \
}

FIXED_LOAD_KERNEL(configured_fixed_load, 32, row * n + it * 32, )
FIXED_LOAD_KERNEL(configured_fixed_load_wrong_index, 32, row * n + it * 32 + 1, )
FIXED_LOAD_KERNEL(configured_fixed_load_changed_n, 32, row * n + it * 32, ++n;)
FIXED_LOAD_KERNEL(configured_fixed_load_changed_pointer, 32, row * n + it * 32, ++input;)

#define LAUNCH_FIXED(NAME, KERNEL) \
GUARDED_CONSTRUCT(NAME, GuardDimsAlias, , composed_width, \
    KERNEL<<<GuardDimsAlias(1, 1, 1), composed_dims>>>(nullptr, nullptr, 128, 128, 2, 0);)

LAUNCH_FIXED(configured_fixed, configured_fixed_load)
LAUNCH_FIXED(configured_fixed_wrong_index, configured_fixed_load_wrong_index)
LAUNCH_FIXED(configured_fixed_changed_n, configured_fixed_load_changed_n)
LAUNCH_FIXED(configured_fixed_changed_pointer, configured_fixed_load_changed_pointer)

// Same fresh source-guard/configuration chain, but its x extent is 16 while
// the selected device labels retain width 32.
int configured_fixed_16(int input) {
    int composed_log = composed_exponent(input);
    const int composed_power = 1 << composed_log;
    int composed_width = guarded_snapshot();
    if (composed_width != 16) stop_now();
    composed_width = composed_power < composed_width ? composed_power : composed_width;
    const int composed_threads = 128;
    int composed_quotient = composed_threads / composed_width;
    GuardDimsAlias composed_dims(composed_width, composed_quotient, 1);
    configured_fixed_load<<<GuardDimsAlias(1, 1, 1), composed_dims>>>(nullptr, nullptr, 128, 128, 2, 0);
    return 0;
}
int configured_fixed_16_caller(int input) {
    const int composed_input = input;
    if (composed_input != 65 && composed_input != 128) return 3;
    configured_fixed_16(composed_input);
    return 0;
}
