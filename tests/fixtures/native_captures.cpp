void ordinary_captures() {
  int first = 3, second = 5;
  auto by_value = [first, second]() { return first + second; };
  auto mixed = [&first, second]() { return first + second; };
  auto nested = [first]() {
    auto inner = [&first]() { return first; };
    return inner();
  };
  auto init = [renamed = first]() { return renamed; };
  (void)by_value(); (void)mixed(); (void)nested(); (void)init();
}
struct Receiver {
  int value;
  int read() { return [this]() { return value; }(); }
};
void initializer_captures() {
  int input = 7;
  auto outer = [value = [input]() { return input; }()]() { return value; };
  (void)outer();
}
