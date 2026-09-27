int unknown_int();

unsigned from_parameter(int value) { return value; }
unsigned from_literal() { return 7; }

template <class T>
unsigned template_literal(T) { return 11; }
template unsigned template_literal<int>(int);
template unsigned template_literal<float>(float);

unsigned increment(int value) { return value++; }
unsigned assignment(int value) { return (value = 3); }
unsigned call() { return unknown_int(); }
unsigned volatile_read(volatile int value) { return value; }
unsigned reference_read(int& value) { return value; }

unsigned from_bool(bool value) { return value; }
unsigned from_float(float value) { return value; }
unsigned from_short(short value) { return value; }
unsigned explicit_cast(int value) { return static_cast<unsigned>(value); }

