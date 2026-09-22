// Deliberately non-unit defaults: never infer missing arguments as one.
typedef struct Defaults {
  unsigned x, y, z;
  Defaults(unsigned a, unsigned b = 7, unsigned c = 13) : x(a), y(b), z(c) {}
} Defaults;
void good() { Defaults value(256); }
extern unsigned opaque();
typedef struct Called {
  unsigned x;
  Called(unsigned a = opaque()) : x(a) {}
} Called;
void called() { Called value; }
typedef struct Redeclared {
  unsigned x, y;
  Redeclared(unsigned a, unsigned b = 19);
} Redeclared;
Redeclared::Redeclared(unsigned a, unsigned b) : x(a), y(b) {}
void redeclared() { Redeclared value(256); }
typedef struct Narrow {
  unsigned char x;
  Narrow(unsigned char a = 300) : x(a) {}
} Narrow;
void narrow() { Narrow value; }
consteval unsigned immediate_value() { return 23; }
typedef struct Immediate {
  unsigned x;
  Immediate(unsigned a = immediate_value()) : x(a) {}
} Immediate;
void immediate() { Immediate value; }
