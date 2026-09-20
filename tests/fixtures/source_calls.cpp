// Source-level frontend regression only; not a GPU benchmark or research corpus.
using Callback = float (*)(float);
float leaf(float value) { return value + 1.0f; }
float apply(Callback callback, float value) { return callback(value); }

float arbitrary_entry(float value) {
  for (int index = 0; index < 3; ++index)
    value = leaf(value);
  return apply(leaf, value);
}

float renamed_entry(float value) {
  for (int index = 0; index < 3; ++index)
    value = leaf(value);
  return apply(leaf, value);
}

float indirect_entry(Callback callback, float value) {
  return callback(leaf(value));
}
