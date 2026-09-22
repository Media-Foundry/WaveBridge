typedef struct PlainValue {
    unsigned x;
    PlainValue(unsigned value) : x(value) {}
} PlainValue;
typedef struct NarrowBits {
    unsigned x : 3;
    NarrowBits(unsigned value) : x(value) {}
} NarrowBits;
typedef struct VolatileValue {
    volatile unsigned x;
    VolatileValue(unsigned value) : x(value) {}
} VolatileValue;
unsigned ordinary() { PlainValue value(99); return value.x; }
unsigned narrowed() { NarrowBits value(99); return value.x; }
unsigned volatile_value() { VolatileValue value(99); return value.x; }
#ifdef WAVEBRIDGE_VALUE_EFFECTS_EXECUTION
int main() { return ordinary() == 99 && narrowed() == 3 ? 0 : 1; }
#endif
