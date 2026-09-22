int cleanup_writes = 0;
const int& minimum_value(const int& a, const int& b) { return a < b ? a : b; }
typedef struct Config {
    unsigned x;
    Config(unsigned value) : x(value) {}
} Config;
struct Temporary {
    operator unsigned() const { return 7; }
    ~Temporary() { ++cleanup_writes; }
};
unsigned scalar_temporary(int count) {
    Config value(minimum_value(count, 1024));
    return value.x;
}
unsigned destructor_temporary() {
    Config value(Temporary{});
    return value.x;
}
unsigned direct_literal() { Config value(7); return value.x; }
unsigned in_lambda(int count) {
    return [&]() { Config value(minimum_value(count, 1024)); return value.x; }();
}
#ifdef WAVEBRIDGE_CLEANUP_EXECUTION
int main() {
    if (cleanup_writes != 0 || scalar_temporary(7) != 7 || cleanup_writes != 0) return 1;
    if (destructor_temporary() != 7 || cleanup_writes != 1) return 2;
    return 0;
}
#endif
