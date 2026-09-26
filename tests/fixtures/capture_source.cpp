typedef struct Plain {
  unsigned x, y;
  Plain(unsigned a, unsigned b) : x(a), y(b) {}
} Plain;

void one_reference() {
  Plain source(3, 5);
  auto f = [&source]() { Plain target(source); };
  f();
}
void nested_references() {
  Plain source(3, 5);
  auto f = [&source]() {
    auto g = [&source]() { Plain target(source); };
    g();
  };
  f();
}
void changed_source() {
  Plain source(3, 5);
  auto f = [&source]() { Plain target(source); };
  source.x = 99;
  f();
}
void initializer_evaluation() {
  Plain source(3, 5);
  auto f = [value = [&source]() { Plain target(source); return 0; }()]() {
    return value;
  };
  (void)f();
}
void outer_copy_inner_reference() {
  Plain source(3, 5);
  auto f = [source]() mutable {
    auto g = [&source]() { Plain target(source); };
    g();
  };
  f();
}
void value_capture() {
  Plain source(3, 5);
  auto f = [source]() mutable { Plain target(source); };
  f();
}
void source_inside_outer() {
  auto f = []() {
    Plain source(3, 5);
    auto g = [&source]() { Plain target(source); };
    g();
  };
  f();
}
void alias_capture() {
  Plain original(3, 5);
  Plain& source = original;
  auto f = [&source]() { Plain target(source); };
  f();
}
void static_source() {
  static Plain source(3, 5);
  auto f = [&]() { Plain target(source); };
  f();
}
void tls_source() {
  thread_local Plain source(3, 5);
  auto f = [&]() { Plain target(source); };
  f();
}
void init_capture() {
  Plain original(3, 5);
  auto f = [source = original]() mutable { Plain target(source); };
  f();
}
void generic_capture() {
  Plain source(3, 5);
  auto f = [&source](auto unused) { Plain target(source); };
  f(1);
}
void direct_without_capture() {
  Plain source(3, 5);
  Plain target(source);
}
void immediate_reference() {
  Plain source(3, 5);
  [&source]() { Plain target(source); }();
}
void immediate_nested() {
  Plain source(3, 5);
  [&]() { [&]() { Plain target(source); }(); }();
}
void named_outer_immediate_inner() {
  Plain source(3, 5);
  auto outer = [&]() { [&]() { Plain target(source); }(); };
  outer();
}
template<class F> void consume_capture(F function) { function(); }
void passed_reference() {
  Plain source(3, 5);
  consume_capture([&]() { Plain target(source); });
}
auto returned_reference() {
  Plain source(3, 5);
  return [&]() { Plain target(source); }; // never executed by tests
}
unsigned immediate_changed_source() {
  Plain source(3, 5);
  return [&]() { source.x = 99; Plain target(source); return target.x; }();
}

#ifdef WAVEBRIDGE_CAPTURE_ORIGIN_EXECUTION
int main() { return immediate_changed_source() == 99 ? 0 : 1; }
#endif
