// Synthetic CUDA frontend fixture, not a GPU workload or a runtime API model.
#include "field_snapshot.cpp"

int cudaConfigureCall(GuardDimsAlias, GuardDimsAlias, unsigned = 0, void* = nullptr);
__attribute__((device)) unsigned long local_leaf(unsigned axis);
__attribute__((device)) unsigned local_x() { return local_leaf(0); }
__attribute__((device)) unsigned local_y() { return local_leaf(1); }
__attribute__((global)) void guarded_target(int value) {
    int local_coordinate_x = local_x();
    int local_coordinate_y = local_y();
}

GUARDED_CONSTRUCT(configured_guard, GuardDimsAlias, , composed_width,
    guarded_target<<<GuardDimsAlias(1, 1, 1), composed_dims>>>(input);)
GUARDED_CONSTRUCT(configured_grid, GuardDimsAlias, , composed_width,
    guarded_target<<<composed_dims, GuardDimsAlias(1, 1, 1)>>>(input);)
GUARDED_CONSTRUCT(configured_write, GuardDimsAlias, , composed_width,
    composed_dims.x = 0;
    guarded_target<<<GuardDimsAlias(1, 1, 1), composed_dims>>>(input);)
