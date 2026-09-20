// Structural call evidence only, no thread-coordinate semantics.
unsigned long external_coordinate(unsigned);
unsigned bridge() { return external_coordinate(0); }
struct Coordinates {
  __declspec(property(get = read)) unsigned x;
  static unsigned read() { return bridge(); }
};
Coordinates coordinates;
unsigned entry() { return coordinates.x; }

struct Dynamic {
  virtual unsigned read() { return bridge(); }
};
unsigned dynamic_entry(Dynamic &object) { return object.read(); }
