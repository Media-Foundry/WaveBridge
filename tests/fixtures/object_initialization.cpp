#include "native_cleanups.cpp"
void static_target() { static Config value(7); }
void tls_target() { thread_local Config value(7); }
void volatile_target() { volatile Config value(7); }
void cleanup_config(Config*) {}
void attributed_target() { Config value __attribute__((cleanup(cleanup_config)))(7); }
void reference_target() { Config original(7); Config& value = original; }
void nested_target(int count) { if (count > 0) { Config value(minimum_value(count, 1024)); } }
void lambda_target(int count) { [&]() { Config value(minimum_value(count, 1024)); }(); }
