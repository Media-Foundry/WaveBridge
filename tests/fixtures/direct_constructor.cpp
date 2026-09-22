// Exact typedef -> record ownership, not a global constructor-name lookup.
typedef struct Shape {
  unsigned x, y, z;
  Shape(unsigned a, unsigned b = 1, unsigned c = 1) : x(a), y(b), z(c) {}
} Shape;
void consume(Shape);
void entry() {
  Shape block(256, 1, 1);
  consume(block);
}
extern unsigned opaque_size();
void dynamic() { Shape block(opaque_size(), 1, 1); consume(block); }
void defaults() { Shape block(256); consume(block); }
namespace other {
typedef struct Shape {
  unsigned x, y, z;
  Shape(unsigned a, unsigned b, unsigned c) : x(a), y(b), z(c) {}
} Shape;
void consume(Shape);
void entry() { Shape block(128, 1, 1); consume(block); }
}
