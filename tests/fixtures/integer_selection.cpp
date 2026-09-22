// Deliberately avoid library/function names as semantic contracts.
template <class T> const T& choose(const T& a, const T& b) {
  return a < b ? a : b;
}
template <class T> const T& reverse_compare(const T& a, const T& b) {
  return b < a ? b : a;
}
const int& not_minimum(const int& a, const int& b) { return a < b ? b : a; }
const int& repeats(const int& a, const int& b) { return a < b ? a : a; }
const int& writes(const int& a, const int& b) {
  const_cast<int&>(a) += 1;
  return a < b ? a : b;
}
extern int opaque();
unsigned good(int count) { return choose(count, 1024); }
unsigned reversed(int count) { return reverse_compare(count, 1024); }
unsigned wrong(int count) { return not_minimum(count, 1024); }
unsigned duplicate(int count) { return repeats(count, 1024); }
unsigned side_effect(int count) { return writes(count, 1024); }
unsigned computed(int count) { return choose(count + 1, 1024); }
unsigned call_argument(int count) { return choose(opaque(), count); }
const int& escapes(int count) { return choose(count, 1024); }
unsigned alias(int& count) { return choose(count, 1024); }
unsigned char narrow(int count) { return choose(count, 1024); }
int signed_result(int count) { return choose(count, 1024); }
int two_variables(int a, int b) { return choose(a, b); }
unsigned long wide(long count) { return choose(count, 1024L); }
