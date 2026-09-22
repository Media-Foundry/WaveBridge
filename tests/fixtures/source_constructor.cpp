template <class T> const T& smaller(const T& a, const T& b) { return a < b ? a : b; }
const int& larger(const int& a, const int& b) { return a < b ? b : a; }
typedef struct Config {
  unsigned x, y, z;
  Config(unsigned a, unsigned b = 7, unsigned c = 13) : x(a), y(b), z(c) {}
} Config;
void dynamic(int count) { Config block(smaller(count, 1024)); }
void constant() { Config block(256); }
void wrong(int count) { Config block(larger(count, 1024)); }
void dual(int a, int b) { Config block(smaller(a, 1024), smaller(b, 512), 3); }
void copy_config(int count) { Config block(smaller(count, 1024)); Config copy(block); }
typedef struct Swapped {
  unsigned x, y, z;
  Swapped(unsigned a, unsigned b = 7, unsigned c = 13) : x(b), y(a), z(c) {}
} Swapped;
void swapped(int count) { Swapped block(smaller(count, 1024)); }
typedef struct Modified {
  unsigned x, y, z;
  Modified(unsigned a, unsigned b = 7, unsigned c = 13) : x(a), y(b), z(c) { x += 1; }
} Modified;
void modified(int count) { Modified block(smaller(count, 1024)); }
