// Structural regression only: these properties have no trusted GPU semantics.
struct Coordinates {
  __declspec(property(get = start_value)) unsigned renamed_start;
  __declspec(property(get = step_value)) unsigned renamed_step;
  static unsigned start_value();
  static unsigned step_value();
};
const Coordinates local_coordinates;
const Coordinates block_coordinates;
void coordinate_columns(int* output, int count) {
  for (int col = local_coordinates.renamed_start; col < count;
       col += block_coordinates.renamed_step)
    output[col] += 1;
}
void changed_body(int* output, int count) {
  for (int col = local_coordinates.renamed_start; col < count;
       col += block_coordinates.renamed_step) {
    output[col] += 1;
    col += 256;
  }
}
void extra_cast(int* output, int count) {
  for (int col = static_cast<short>(local_coordinates.renamed_start); col < count;
       col += block_coordinates.renamed_step)
    output[col] += 1;
}
void arithmetic_step(int* output, int count) {
  for (int col = local_coordinates.renamed_start; col < count;
       col += block_coordinates.renamed_step + 1)
    output[col] += 1;
}
using HiddenReference = int&;
void reference_body(int* output, int count) {
  for (int col = local_coordinates.renamed_start; col < count;
       col += block_coordinates.renamed_step) {
    output[col] += 1;
    HiddenReference alias = col;
    alias += 256;
  }
}
void changed_bound(int* output, int count) {
  for (int col = local_coordinates.renamed_start; col < count;
       col += block_coordinates.renamed_step) {
    output[col] += 1;
    --count;
  }
}
extern void opaque_effect();
void called_body(int* output, int count) {
  for (int col = local_coordinates.renamed_start; col < count;
       col += block_coordinates.renamed_step) {
    output[col] += 1;
    opaque_effect();
  }
}
