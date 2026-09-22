typedef struct PlainValue {
  unsigned x;
  PlainValue(unsigned value) : x(value) {}
} PlainValue;

unsigned no_publication() {
  PlainValue source(3);
  PlainValue target(source);
  return target.x;
}

typedef struct BodyPublished {
  static BodyPublished* published;
  unsigned x;
  BodyPublished(unsigned value) : x(value) { published = this; }
} BodyPublished;
BodyPublished* BodyPublished::published = nullptr;
void mutate_body_publication() { BodyPublished::published->x = 99; }
unsigned body_publication() {
  BodyPublished source(3);
  mutate_body_publication();
  BodyPublished target(source);
  return target.x;
}

typedef struct InitializerPublished {
  static InitializerPublished* published;
  unsigned x;
  static unsigned publish(InitializerPublished* object, unsigned value) {
    published = object;
    return value;
  }
  InitializerPublished(unsigned value) : x(publish(this, value)) {}
} InitializerPublished;
InitializerPublished* InitializerPublished::published = nullptr;
void mutate_initializer_publication() { InitializerPublished::published->x = 99; }
unsigned initializer_publication() {
  InitializerPublished source(3);
  mutate_initializer_publication();
  InitializerPublished target(source);
  return target.x;
}

#ifdef WAVEBRIDGE_ESCAPE_EXECUTION
int main() {
  if (no_publication() != 3) return 1;
  if (body_publication() != 99) return 2;
  if (initializer_publication() != 99) return 3;
  return 0;
}
#endif
