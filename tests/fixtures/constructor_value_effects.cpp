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
int initialization_writes = 0;
int initialize_operand() { ++initialization_writes; return 7; }
thread_local int operand = initialize_operand();
const int& minimum_value(const int& a, const int& b) { return a < b ? a : b; }
unsigned tls_argument() { PlainValue value(minimum_value(operand, 1024)); return value.x; }
#ifdef WAVEBRIDGE_VALUE_EFFECTS_EXECUTION
int main() {
    if (ordinary() != 99 || narrowed() != 3) return 1;
    if (initialization_writes != 0) return 2;
    if (tls_argument() != 7 || initialization_writes != 1) return 3;
    if (tls_argument() != 7 || initialization_writes != 1) return 4;
    return 0;
}
#endif
