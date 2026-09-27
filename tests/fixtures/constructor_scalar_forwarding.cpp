typedef struct Forwarded {
  unsigned x, y, z;
  Forwarded(unsigned a, unsigned b, unsigned c) : x(a), y(b), z(c) {}
} ForwardedAlias;

typedef struct Swapped {
  unsigned x, y, z;
  Swapped(unsigned a, unsigned b, unsigned c) : x(b), y(a), z(c) {}
} SwappedAlias;

typedef struct BodyWrite {
  unsigned x, y, z;
  BodyWrite(unsigned a, unsigned b, unsigned c) : x(a), y(b), z(c) { x = 0; }
} BodyWriteAlias;

typedef struct ParameterWrite {
  unsigned x, y, z;
  ParameterWrite(unsigned a, unsigned b, unsigned c) : x(a++), y(b), z(c) {}
} ParameterWriteAlias;

typedef struct NarrowField {
  unsigned short x;
  unsigned y, z;
  NarrowField(unsigned a, unsigned b, unsigned c) : x(a), y(b), z(c) {}
} NarrowFieldAlias;

typedef struct Defaults {
  unsigned x, y, z;
  Defaults(unsigned a, unsigned b, unsigned c = 1) : x(a), y(b), z(c) {}
} DefaultsAlias;

int opaque();

void forwarded(int a, int b, int c) { ForwardedAlias value(a, b, c); }
void swapped(int a, int b, int c) { SwappedAlias value(a, b, c); }
void body_write(int a, int b, int c) { BodyWriteAlias value(a, b, c); }
void parameter_write(int a, int b, int c) { ParameterWriteAlias value(a, b, c); }
void call_argument(int a, int b) { ForwardedAlias value(a, opaque(), b); }
void narrow_field(int a, int b, int c) { NarrowFieldAlias value(a, b, c); }
void default_argument(int a, int b) { DefaultsAlias value(a, b); }

