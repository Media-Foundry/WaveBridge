// MS property AST regression; no external function is executed or trusted.
extern unsigned long external_id(unsigned dimension);
unsigned wrapper() { return external_id(0); }
struct Holder {
  __declspec(property(get = getter)) unsigned index;
  unsigned getter() { return wrapper(); }
};
Holder holder;
struct StaticHolder {
  __declspec(property(get = accessor)) unsigned renamed_property;
  static unsigned accessor() { return wrapper(); }
};
const StaticHolder static_holder;
void entry() {
  const int original = holder.index;
  const int renamed = holder.index;
  const int with_arithmetic = wrapper() + 1;
  int mutable_value = holder.index;
  const int static_property = static_holder.renamed_property;
  const int static_arithmetic = static_holder.renamed_property + 1;
}
