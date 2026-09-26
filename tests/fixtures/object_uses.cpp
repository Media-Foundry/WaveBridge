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
unsigned unreachable_copy_count = 0;
void unreachable_copy_flow() {
  if (false) {
    Config source(3);
    [&]() { Config target(source); ++unreachable_copy_count; }();
  }
}
unsigned cleanup_observation_count = 0;
struct SideEffectTemporary {
  ~SideEffectTemporary() { ++cleanup_observation_count; }
};
void side_effect_cleanup_copy() {
  Config source(3);
  (SideEffectTemporary{}, [&]() { Config target(source); }());
}
void standalone_temporary_before_copy() {
  Config source(3);
  SideEffectTemporary{};
  observe_value(source);
}
void scalar_cleanup_before_copy() {
  Config source(3);
  const int& scalar_temporary = 7;
  (void)scalar_temporary;
  observe_value(source);
}
void cleanup_between_two_copies() {
  Config source(3);
  observe_value(source);
  const int& scalar_temporary = 7;
  (void)scalar_temporary;
  observe_value(source);
}
void cleanup_in_uncalled_lambda() {
  Config source(3);
  auto unused = [] { SideEffectTemporary{}; };
  (void)unused;
  observe_value(source);
}
void cleanup_in_opposite_if_branch(bool select_cleanup) {
  Config source(3);
  if (select_cleanup)
    SideEffectTemporary{};
  else
    observe_value(source);
}
void ended_scope_before_copy() {
  Config source(3);
  { SideEffectTemporary local; }
  observe_value(source);
}
void local_cleanup_enclosing_lambda() {
  Config source(3);
  SideEffectTemporary guard_before;
  [&]() { observe_value(source); }();
  SideEffectTemporary guard_after;
}
void local_cleanup_disjoint_scopes() {
  Config source(3);
  { SideEffectTemporary nested_before; }
  observe_value(source);
  { SideEffectTemporary nested_after; }
}
void local_cleanup_same_declaration() {
  Config source(3);
  Config peer(4), target(source);
  (void)target;
}
void local_cleanup_static_unrelated() {
  Config source(3);
  static SideEffectTemporary unrelated_static;
  observe_value(source);
}
void local_cleanup_if_else(bool select_cleanup) {
  Config source(3);
  if (select_cleanup) {
    SideEffectTemporary then_scope;
  } else {
    observe_value(source);
  }
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

// A real declaration outside the local effect subset; no claim that the
// diagnostic attribute itself changes runtime semantics.
typedef struct AttributedCopy {
  unsigned x;
  AttributedCopy(unsigned value) : x(value) {}
  AttributedCopy(const AttributedCopy& other [[maybe_unused]]) : x(other.x) {}
} AttributedCopy;
void attributed_copy_flow() { AttributedCopy source(3); AttributedCopy target(source); }
void captured_attributed_copy_flow() {
  AttributedCopy source(3);
  [&]() { AttributedCopy target(source); }();
}

#ifdef WAVEBRIDGE_OBJECT_USES_EXECUTION
void opaque_call() {}
int main() {
  unreachable_copy_flow();
  if (unreachable_copy_count != 0) return 4;
  by_value_flow();
  if (observed_value != 3 || mutation_calls != 1) return 1;
  captured_by_value_flow();
  if (observed_value != 3 || mutation_calls != 2) return 2;
  by_reference_flow();
  if (observed_value != 99 || mutation_calls != 3) return 3;
  cleanup_observation_count = 0;
  standalone_temporary_before_copy();
  if (cleanup_observation_count != 1 || observed_value != 3) return 5;
  ended_scope_before_copy();
  if (cleanup_observation_count != 2 || observed_value != 3) return 6;
  cleanup_in_uncalled_lambda();
  if (cleanup_observation_count != 2 || observed_value != 3) return 7;
  return 0;
}
#endif
