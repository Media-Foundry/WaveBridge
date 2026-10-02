// Synthetic CUDA frontend fixture, not a GPU workload or a runtime API model.
#include "field_snapshot.cpp"

int cudaConfigureCall(GuardDimsAlias, GuardDimsAlias, unsigned = 0, void* = nullptr);
__attribute__((device)) unsigned long local_leaf(unsigned axis);
__attribute__((device)) unsigned local_x() { return local_leaf(0); }
__attribute__((device)) unsigned local_y() { return local_leaf(1); }
__attribute__((global)) void guarded_target(int value) {
    int local_coordinate_y = local_y();
    int local_coordinate_x = local_x();
    int offset = local_coordinate_x + value;
    for (int column = 0; column < 4; ++column) {
        int element = offset + column * 32;
    }
}

#define COORDINATE_TARGET(NAME, BEFORE, BODY) \
__attribute__((global)) void NAME(int value) { \
    int local_coordinate_y = local_y(); \
    int local_coordinate_x = local_x(); \
    BEFORE \
    for (int column = 0; column < 4; ++column) { BODY } \
}
COORDINATE_TARGET(changed_coordinate, ++local_coordinate_x;, )
COORDINATE_TARGET(aliased_coordinate, using Ref = int&; Ref alias = local_coordinate_x; ++alias;, )
COORDINATE_TARGET(body_changed_coordinate, , ++local_coordinate_x;)
COORDINATE_TARGET(opaque_coordinate, int later = local_y();, )

GUARDED_CONSTRUCT(configured_guard, GuardDimsAlias, , composed_width,
    guarded_target<<<GuardDimsAlias(1, 1, 1), composed_dims>>>(input);)
GUARDED_CONSTRUCT(configured_grid, GuardDimsAlias, , composed_width,
    guarded_target<<<composed_dims, GuardDimsAlias(1, 1, 1)>>>(input);)
GUARDED_CONSTRUCT(configured_write, GuardDimsAlias, , composed_width,
    composed_dims.x = 0;
    guarded_target<<<GuardDimsAlias(1, 1, 1), composed_dims>>>(input);)
GUARDED_CONSTRUCT(configured_changed_coordinate, GuardDimsAlias, , composed_width,
    changed_coordinate<<<GuardDimsAlias(1, 1, 1), composed_dims>>>(input);)
GUARDED_CONSTRUCT(configured_aliased_coordinate, GuardDimsAlias, , composed_width,
    aliased_coordinate<<<GuardDimsAlias(1, 1, 1), composed_dims>>>(input);)
GUARDED_CONSTRUCT(configured_body_changed_coordinate, GuardDimsAlias, , composed_width,
    body_changed_coordinate<<<GuardDimsAlias(1, 1, 1), composed_dims>>>(input);)
GUARDED_CONSTRUCT(configured_opaque_coordinate, GuardDimsAlias, , composed_width,
    opaque_coordinate<<<GuardDimsAlias(1, 1, 1), composed_dims>>>(input);)
