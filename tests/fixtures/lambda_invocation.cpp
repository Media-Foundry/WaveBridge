typedef struct Config {
  unsigned x;
  Config(unsigned value) : x(value) {}
} Config;

int direct() { return []() { return 7; }(); }
int parens() { return ([]() { return 7; })(); }
int trailing_return() { return []() -> int { return 7; }(); }
void trailing_void() { []() -> void {}(); }
int mutable_direct() { return [value = 7]() mutable { return ++value; }(); }
int nested(int count) {
  return [&]() { return [&]() { return count; }(); }();
}
int named() { auto f = []() { return 7; }; return f(); }
auto returned() { return []() { return 7; }; }
template<class F> int consume(F f) { return f(); }
int passed() { return consume([]() { return 7; }); }
int explicit_argument() { return [](int value) { return value; }(7); }
int default_argument() { return [](int value = 7) { return value; }(); }
int generic() { return [](auto value) { return value; }(7); }
int explicit_member() { return []() { return 7; }.operator()(); }
unsigned mutating_body() {
  Config source(3);
  return [&]() { source.x = 99; Config target(source); return target.x; }();
}
int unreachable() { if (false) return []() { return 99; }(); return 7; }

#ifdef WAVEBRIDGE_INVOCATION_EXECUTION
int main() {
  if (direct() != 7 || parens() != 7 || mutable_direct() != 8 || nested(5) != 5) return 1;
  if (mutating_body() != 99) return 2;
  if (unreachable() != 7) return 3;
  return 0;
}
#endif
