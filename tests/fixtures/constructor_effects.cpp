#include "constructor_escape.cpp"

struct LiteralField { unsigned x; LiteralField() : x(7) {} };
struct ConvertedField { unsigned char x; ConvertedField(unsigned v) : x(v) {} };
struct PointerField { unsigned* x; PointerField(unsigned* v) : x(v) {} };
struct ReferenceField { unsigned& x; ReferenceField(unsigned& v) : x(v) {} };
struct VolatileField { volatile unsigned x; VolatileField(unsigned v) : x(v) {} };
struct BitField { unsigned x : 3; BitField(unsigned v) : x(v) {} };
struct BaseField : PlainValue { BaseField(unsigned v) : PlainValue(v) {} };
struct VirtualField {
  unsigned x;
  VirtualField(unsigned v) : x(v) {}
  virtual ~VirtualField() {}
};
union UnionField { unsigned x; UnionField(unsigned v) : x(v) {} };
struct ReferenceParameter { unsigned x; ReferenceParameter(const unsigned& v) : x(v) {} };
struct BodyWrite { unsigned x; BodyWrite(unsigned v) : x(v) { x += 1; } };
struct ArithmeticField { unsigned x; ArithmeticField(unsigned v) : x(v + 1) {} };
struct ThisRead { unsigned x, y; ThisRead(unsigned v) : x(v), y(x) {} };

void effects_entry() {
  LiteralField literal;
  ConvertedField converted(257);
}
