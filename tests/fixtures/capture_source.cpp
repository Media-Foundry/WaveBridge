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
