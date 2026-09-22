template <class T> const T& select_min(const T& a, const T& b) { return a < b ? a : b; }
typedef struct Config {
    unsigned x, y;
    Config(unsigned a, unsigned b = 1) : x(a), y(b) {}
} Config;
void constant() { Config value(7); }
void dynamic(int count) { Config value(select_min(count, 1024)); }
void local() { int count = 7; Config value(select_min(count, 1024)); }
int writes = 0;
int initialize() { ++writes; return 7; }
void earlier_initialization() { int count = initialize(); Config value(select_min(count, 1024)); }
int global_count = 7;
thread_local int tls_count = initialize();
extern int external_count;
void global_argument() { Config value(select_min(global_count, 1024)); }
void tls_argument() { Config value(select_min(tls_count, 1024)); }
void extern_argument() { Config value(select_min(external_count, 1024)); }
void static_argument() { static int count = initialize(); Config value(select_min(count, 1024)); }
void local_tls_argument() { thread_local int count = initialize(); Config value(select_min(count, 1024)); }
void captured(int count) { [&]() { Config value(select_min(count, 1024)); }(); }
void reference_argument(int& count) { Config value(select_min(count, 1024)); }
void cleanup_integer(int*) {}
void cleanup_argument() {
    int count __attribute__((cleanup(cleanup_integer))) = 7;
    Config value(select_min(count, 1024));
}
template <class T> void template_caller(T count) { Config value(select_min(count, 1024)); }
void instantiate() { template_caller<int>(7); }
const int& enabled_min(const int& a, const int& b) __attribute__((enable_if(true, "enabled"))) {
    return a < b ? a : b;
}
void enabled_argument(int count) { Config value(enabled_min(count, 1024)); }
