typedef struct Plain {
  unsigned x, y, z;
  Plain(unsigned a, unsigned b, unsigned c) : x(a), y(b), z(c) {}
} Plain;
void implicit_copy() { Plain source(3, 5, 7); Plain target(source); }
void parameter_copy(Plain source) { Plain target(source); }
void alias_copy() { Plain source(3, 5, 7); Plain& alias = source; Plain target(alias); }
void changed_before_copy() { Plain source(3, 5, 7); source.x = 99; Plain target(source); }
void captured_copy() {
  Plain source(3, 5, 7);
  auto f = [source]() mutable { Plain target(source); };
  source.x = 99;
  f();
}
typedef struct Manual {
  unsigned x, y;
  Manual() : x(3), y(5) {}
  Manual(const Manual& source) : x(source.x), y(source.y) {}
} Manual;
void manual_copy() { Manual source; Manual target(source); }
typedef struct Swapped {
  unsigned x, y;
  Swapped() : x(3), y(5) {}
  Swapped(const Swapped& source) : x(source.y), y(source.x) {}
} Swapped;
void swapped_copy() { Swapped source; Swapped target(source); }
typedef struct Writes {
  unsigned x;
  Writes() : x(3) {}
  Writes(const Writes& source) : x(source.x) { x += 1; }
} Writes;
void writing_copy() { Writes source; Writes target(source); }
typedef struct Bits { unsigned x : 3; } Bits;
void bitfield_copy() { Bits source{3}; Bits target(source); }
typedef struct Volatile { volatile unsigned x; } Volatile;
void volatile_copy() { Volatile source{3}; Volatile target(source); }
typedef union United { unsigned x, y; } United;
void union_copy() { United source{3}; United target(source); }
typedef struct Pointer { int* x; } Pointer;
void pointer_copy() { Pointer source{nullptr}; Pointer target(source); }
typedef struct Polymorphic {
  unsigned x;
  Polymorphic() : x(3) {}
  virtual ~Polymorphic() {}
} Polymorphic;
void polymorphic_copy() { Polymorphic source; Polymorphic target(source); }
