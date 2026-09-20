// Constructor spelling and argument positions do not imply GPU dimension semantics.
struct Dimensions {
  unsigned a, b, c;
  constexpr Dimensions(unsigned first = 1, unsigned second = 1, unsigned third = 1)
      : a(first), b(second), c(third) {}
};
constexpr int threads = 256;
void consume(Dimensions);
void entry() { consume(Dimensions(threads, 1, 1)); }
void defaults() { consume(Dimensions(threads)); }
