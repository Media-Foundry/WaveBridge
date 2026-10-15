// Scalar source fixture only; this is not a GPU execution or API model.
extern unsigned long group_size_leaf(int axis);
extern unsigned long group_id_leaf(int axis);
extern unsigned long local_id_leaf(int axis);
extern void opaque();

using size_type = unsigned long;
extern size_type group_size_leaf_uint(unsigned int axis);
extern size_type group_id_leaf_uint(unsigned int axis);
extern size_type local_id_leaf_uint(unsigned int axis);

unsigned size_y() { return group_size_leaf(1); }
unsigned group_x() { return group_id_leaf(0); }
unsigned local_y() { return local_id_leaf(1); }
unsigned local_x() { return local_id_leaf(0); }
unsigned size_y_uint() { return group_size_leaf_uint(1); }
unsigned group_x_uint() { return group_id_leaf_uint(0); }
unsigned local_y_uint() { return local_id_leaf_uint(1); }

unsigned property_size_y() { return group_size_leaf(1); }
struct PropertyDimensions {
    __declspec(property(get = get_y)) unsigned y;
    static unsigned get_y() { return property_size_y(); }
};
extern const PropertyDimensions property_dimensions;
extern const volatile PropertyDimensions volatile_property_dimensions;
extern unsigned unknown_unsigned();
struct UnknownPropertyDimensions {
    __declspec(property(get = get_y)) unsigned y;
    static unsigned get_y() { return unknown_unsigned(); }
};
extern const UnknownPropertyDimensions unknown_property_dimensions;

#define PREFIX int row = (size_y() * group_x() + local_y()) * 2; \
               int local_batches = batch - row; \
               if (local_batches > 2) local_batches = 2;

void good(int batch) { PREFIX int stop = 0; (void)stop; }
using Value = int;
using Ref = int&;
void value_alias(int batch) { PREFIX Value alias = local_batches; int stop = 0; (void)stop; }
void common_write(int batch) { PREFIX local_batches = 1; int stop = 0; (void)stop; }
void post_write(int batch) { PREFIX int stop = 0; local_batches = 0; (void)stop; }
void post_loop(int batch) { PREFIX int stop = 0; for (int k=0;k<2;++k) local_batches += k; (void)stop; }

void varying_value(int batch) {
    PREFIX
    unsigned x = local_x();
    local_batches += (int)x;
    int stop = 0; (void)stop;
}
void varying_if(int batch) {
    PREFIX
    unsigned x = local_x();
    if (x) local_batches = 1;
    int stop = 0; (void)stop;
}
void varying_if_two_constants(int batch) {
    PREFIX
    unsigned x = local_x();
    if (x) local_batches = 1; else local_batches = 2;
    int stop = 0; (void)stop;
}
void varying_if_unrelated(int batch) {
    PREFIX
    unsigned x = local_x();
    int unrelated = 0;
    if (x) unrelated = 1; else unrelated = 2;
    int stop = 0; (void)stop; (void)unrelated;
}
void unknown_call(int batch) { PREFIX opaque(); int stop = 0; (void)stop; }
void reference_alias(int batch) { PREFIX Ref alias = local_batches; int stop = 0; (void)stop; }
void static_local(int batch) { PREFIX static int saved = local_batches; int stop = 0; (void)stop; }
void tls_local(int batch) { PREFIX thread_local int saved = local_batches; int stop = 0; (void)stop; }
void address_escape(int batch) { PREFIX int* escaped = &local_batches; int stop = 0; (void)stop; }
void goto_after(int batch) { PREFIX int stop = 0; goto done; done: (void)stop; }

// The selected declaration is not evaluated by the prefix checker.
void target_writes(int batch) {
    PREFIX
    int stop = (++local_batches, 0);
    (void)stop;
}
void uint_axis_good(int batch) {
    int row = (size_y_uint() * group_x_uint() + local_y_uint()) * 2;
    int local_batches = batch - row;
    if (local_batches > 2) local_batches = 2;
    int stop = 0; (void)stop;
}

#define PROPERTY_PREFIX(OBJECT) int row = (OBJECT.y * group_x() + local_y()) * 2; \
                                int local_batches = batch - row; \
                                if (local_batches > 2) local_batches = 2;
void property_good(int batch) { PROPERTY_PREFIX(property_dimensions) int stop = 0; (void)stop; }
void property_wrong_receiver(int batch) { PROPERTY_PREFIX(volatile_property_dimensions) int stop = 0; (void)stop; }
void property_unknown_wrapper(int batch) { PROPERTY_PREFIX(unknown_property_dimensions) int stop = 0; (void)stop; }
