#include <new>

typedef struct Plain {
  unsigned x, y, z;
  Plain(unsigned a, unsigned b, unsigned c) : x(a), y(b), z(c) {}
} Plain;
void implicit_copy() { Plain source(3, 5, 7); Plain target(source); }
void parameter_copy(Plain source) { Plain target(source); }
#if !defined(WAVEBRIDGE_CAPTURE_EXECUTION) && !defined(WAVEBRIDGE_REBUILD_COPY_EXECUTION)
void accept_value(int prefix, Plain value);
void differently_named(Plain value);
void accept_reference(const Plain& value);
template<class T> void accept_generic(T value);
void argument_copy() { Plain source(3, 5, 7); accept_value(0, source); }
void renamed_argument_copy() { Plain source(3, 5, 7); differently_named(source); }
void indirect_argument_copy() { Plain source(3, 5, 7); auto f = &accept_value; f(0, source); }
void reference_argument_copy() { Plain source(3, 5, 7); accept_reference(Plain(source)); }
void generic_argument_copy() { Plain source(3, 5, 7); accept_generic(source); }
#endif
void alias_copy() { Plain source(3, 5, 7); Plain& alias = source; Plain target(alias); }
void changed_before_copy() { Plain source(3, 5, 7); source.x = 99; Plain target(source); }
unsigned captured_copy() {
  Plain source(3, 5, 7);
  auto f = [source]() mutable { Plain target(source); return target.x; };
  source.x = 99;
  return f();
}
unsigned reference_captured_copy() {
  Plain source(3, 5, 7);
  auto f = [&source]() { Plain target(source); return target.x; };
  source.x = 99;
  return f();
}
unsigned nested_captured_copy() {
  Plain source(3, 5, 7);
  auto f = [source]() mutable {
    auto g = [&source]() { Plain target(source); return target.x; };
    return g();
  };
  source.x = 99;
  return f();
}
typedef struct Manual {
  unsigned x, y;
  Manual() : x(3), y(5) {}
  Manual(const Manual& source) : x(source.x), y(source.y) {}
} Manual;
void manual_copy() { Manual source; Manual target(source); }
typedef struct ParameterAttribute {
  unsigned x;
  ParameterAttribute() : x(3) {}
  ParameterAttribute(const ParameterAttribute& source __attribute__((unused))) : x(source.x) {}
} ParameterAttribute;
void parameter_attribute_copy() { ParameterAttribute source; ParameterAttribute target(source); }
#ifdef WAVEBRIDGE_CUDA_COPY
typedef struct CudaAnnotated {
  unsigned x;
  __attribute__((host, device)) CudaAnnotated() : x(3) {}
  __attribute__((host, device)) CudaAnnotated(const CudaAnnotated& source) : x(source.x) {}
} CudaAnnotated;
void cuda_annotated_copy() { CudaAnnotated source; CudaAnnotated target(source); }
#endif
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

// A real, valid counterexample to treating outer DeclRef closure as a
// lifetime proof: the copy constructor can reach the source through its own
// const-reference parameter, end that lifetime, and rebuild the object in the
// same storage without another outer reference to `source`.
typedef struct Rebuilding {
  unsigned x;
  Rebuilding(unsigned value) : x(value) {}
  Rebuilding(const Rebuilding& other) : x(other.x) {
    Rebuilding* pointer = const_cast<Rebuilding*>(&other);
    pointer->~Rebuilding();
    ::new (pointer) Rebuilding(99);
  }
  ~Rebuilding() {}
} Rebuilding;
unsigned rebuilding_copy() {
  Rebuilding source(3);
  Rebuilding target(source);
  Rebuilding second(source);
  return target.x + second.x;
}

#ifdef WAVEBRIDGE_REBUILD_COPY_EXECUTION
int main() { return rebuilding_copy() == 102 ? 0 : 1; }
#endif

#ifdef WAVEBRIDGE_CAPTURE_EXECUTION
int main() {
  if (captured_copy() != 3) return 1;
  if (reference_captured_copy() != 99) return 2;
  if (nested_captured_copy() != 3) return 3;
  return 0;
}
#endif
