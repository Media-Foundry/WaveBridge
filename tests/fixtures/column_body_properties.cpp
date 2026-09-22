// CPU frontend fixture only; leaf semantics are explicit test assumptions.
extern unsigned leaf();
extern void opaque_effect();
struct Coordinates {
  static unsigned get() { return leaf(); }
  __declspec(property(get = get)) unsigned value;
};
extern const Coordinates start_object;
extern const Coordinates step_object;
extern const Coordinates row_object;
using HiddenReference = int&;

#define LOOP for (int col = start_object.value; col < count; col += step_object.value)
#define STORE output[col + row_object.value] += 1
void good(int* output, int count) { LOOP { STORE; } }
void two_properties(int* output, int count) {
  LOOP { STORE; output[col + row_object.value] += 2; }
}
void changed_induction(int* output, int count) { LOOP { STORE; col += 256; } }
void changed_bound(int* output, int count) { LOOP { STORE; --count; } }
void hidden_reference(int* output, int count) {
  LOOP { STORE; HiddenReference alias = col; alias += 256; }
}
void opaque_body(int* output, int count) { LOOP { STORE; opaque_effect(); } }
void nested_loop(int* output, int count) { LOOP { STORE; for (int k=0; k<2; ++k) {} } }
void comma_target(int* output, int count) { LOOP { STORE; (void(), col) += 256; } }
void changed_index(int* output, int count) {
  LOOP { output[col++ + row_object.value] += 1; }
}
void read_only_cast(int* output, int count) {
  LOOP { output[static_cast<int>(col) + row_object.value] += 1; }
}
void static_induction(int* output, int count) {
  for (static int col = start_object.value; col < count; col += step_object.value) { STORE; }
}
void nested_context(int* output, int count) { if (count) { LOOP { STORE; } } }
