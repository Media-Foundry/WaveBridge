typedef struct Config {
  unsigned x;
  Config(unsigned value) : x(value) {}
} Config;

void plain_copy() {
  Config source(3);
  Config target(source);
}
void three_branches(int branch) {
  Config source(3);
  [&]() {
    if (branch == 0) { [&]() { Config target(source); }(); }
    else if (branch == 1) { [&]() { Config target(source); }(); }
    else { [&]() { Config target(source); }(); }
  }();
}
void direct_write() {
  Config source(3);
  source.x = 99;
  Config target(source);
}
void write_inside_lambda() {
  Config source(3);
  [&]() { source.x = 99; Config target(source); }();
}
void write_in_other_branch(bool branch) {
  Config source(3);
  if (branch) { Config target(source); }
  else { source.x = 99; }
}
void reference_alias() {
  Config source(3);
  using Alias = Config&;
  Alias alias = source;
  alias.x = 99;
  Config target(source);
}
void cast_alias() {
  Config source(3);
  static_cast<Config&>(source).x = 99;
  Config target(source);
}
void mutate(Config* object) { object->x = 99; }
void address_escape() {
  Config source(3);
  mutate(&source);
  Config target(source);
}
void by_value_capture() {
  Config source(3);
  [source]() { Config target(source); }();
}
void named_closure() {
  Config source(3);
  auto f = [&]() { Config target(source); };
  f();
}
template<class F> void forward(F function) { function(); }
void passed_closure() {
  Config source(3);
  forward([&]() { Config target(source); });
}
void init_capture_alias() {
  Config source(3);
  [&alias = source]() { Config target(alias); }();
}
void opaque_assembly() {
  Config source(3);
  asm volatile("" : : : "memory");
  Config target(source);
}
void opaque_call();
void ordinary_opaque_call() {
  Config source(3);
  opaque_call();
  Config target(source);
}
void static_source() {
  static Config source(3);
  Config target(source);
}
void tls_source() {
  thread_local Config source(3);
  Config target(source);
}
