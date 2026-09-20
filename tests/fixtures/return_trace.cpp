// Structural call-chain regression; these names carry no hardware semantics.
extern unsigned long external_index(unsigned dimension);
unsigned wrapper() { return external_index(0); }
unsigned renamed_wrapper() { return external_index(1); }
struct Holder {
  unsigned getter() { return wrapper(); }
  unsigned alternate() { return renamed_wrapper(); }
};
unsigned arithmetic_getter() { return wrapper() + 1; }
unsigned multi_statement() { unsigned value = wrapper(); return value; }
