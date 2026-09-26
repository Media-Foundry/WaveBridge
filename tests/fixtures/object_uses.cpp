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

// The callee is deliberately impure: parameter writes and a global counter.
unsigned observed_value = 0;
unsigned mutation_calls = 0;
void change_value(Config value) { ++mutation_calls; value.x = 99; }
void observe_value(Config value) { observed_value = value.x; }
void change_reference(Config& value) { ++mutation_calls; value.x = 99; }
void by_value_flow() {
  Config source(3);
  change_value(source);
  observe_value(source);
}
void captured_by_value_flow() {
  Config source(3);
  [&]() { change_value(source); observe_value(source); }();
}
void by_reference_flow() {
  Config source(3);
  change_reference(source);
  observe_value(source);
}
void nested_scope_flow() {
  { Config source(3); observe_value(source); }
}
void loop_flow() {
  Config source(3);
  for (int i = 0; i < 2; ++i) observe_value(source);
}
void goto_flow() {
  Config source(3);
  goto after;
after:
  observe_value(source);
}
void try_flow() {
  Config source(3);
  try { observe_value(source); } catch (...) {}
}
void switch_flow(int branch) {
  Config source(3);
  switch (branch) {
    case 0: observe_value(source); break;
    default: observe_value(source); break;
  }
}
void switch_before_source(int branch) {
  switch (branch) { case 0: break; default: break; }
  Config source(3);
  observe_value(source);
}
void do_false_flow() { Config source(3); do { observe_value(source); } while (false); }
void do_zero_flow() { Config source(3); do { observe_value(source); } while (0); }
void do_break_flow() { Config source(3); do { observe_value(source); break; } while (false); }
void do_dynamic_flow(bool repeat) { Config source(3); do { observe_value(source); } while (repeat); }
void do_true_flow() { Config source(3); do { observe_value(source); break; } while (true); }
void do_continue_flow() { Config source(3); do { observe_value(source); continue; } while (false); }
void do_before_source() { do {} while (false); Config source(3); observe_value(source); }
void do_nested_switch(int branch) {
  Config source(3);
  do { switch (branch) { case 0: observe_value(source); break; default: break; } } while (false);
}
void case_into_do(int branch) {
  Config source(3);
  switch (branch) { do { case 0: observe_value(source); break; } while (false); }
}

#ifdef WAVEBRIDGE_OBJECT_USES_EXECUTION
void opaque_call() {}
int main() {
  by_value_flow();
  if (observed_value != 3 || mutation_calls != 1) return 1;
  captured_by_value_flow();
  if (observed_value != 3 || mutation_calls != 2) return 2;
  by_reference_flow();
  if (observed_value != 99 || mutation_calls != 3) return 3;
  return 0;
}
#endif
