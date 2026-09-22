// Structural fixture: the external leaf's value/effect is never inferred here.
extern unsigned leaf();
struct Holder {
  __declspec(property(get = get)) unsigned value;
  static unsigned get() { return leaf(); }
};
extern const Holder object;
extern const volatile Holder volatile_object;
extern thread_local const Holder tls_object;
using Reference = const Holder&;
extern Reference alias_object;
static const Holder internal_object;
extern Holder& make_object();

unsigned good() { return object.value; }
unsigned volatile_case() { return volatile_object.value; }
unsigned tls_case() { return tls_object.value; }
unsigned alias_case() { return alias_object.value; }
unsigned internal_case() { return internal_object.value; }
unsigned called_receiver() { return make_object().value; }
