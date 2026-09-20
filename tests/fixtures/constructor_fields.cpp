struct Permuted {
  unsigned left, right;
  Permuted(unsigned first, unsigned second) : left(second), right(first) {}
};
struct BodyWrites {
  unsigned value;
  BodyWrites(unsigned input) : value(input) { ++value; }
};
void entry() {}
