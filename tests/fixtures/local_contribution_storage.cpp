// CPU/Clang regression only. No GPU or collective semantics are assumed.
float combine(float value, float *) { return value; }

float automatic(const float *input, int count, const int start) {
  float partial = 0.0f;
  for (int col = start; col < count; col += 1) {
    const float value = input[col];
    partial += value * value;
  }
  float scratch[32];
  const float total = combine(partial, scratch);
  return total;
}

float static_accumulator(const float *input, int count, const int start) {
  static float partial = 0.0f;
  for (int col = start; col < count; col += 1) {
    const float value = input[col];
    partial += value * value;
  }
  float scratch[32];
  const float total = combine(partial, scratch);
  return total;
}

float thread_accumulator(const float *input, int count, const int start) {
  thread_local float partial = 0.0f;
  for (int col = start; col < count; col += 1) {
    const float value = input[col];
    partial += value * value;
  }
  float scratch[32];
  const float total = combine(partial, scratch);
  return total;
}

float static_load(const float *input, int count, const int start) {
  float partial = 0.0f;
  for (int col = start; col < count; col += 1) {
    static const float value = input[col];
    partial += value * value;
  }
  float scratch[32];
  const float total = combine(partial, scratch);
  return total;
}

float thread_load(const float *input, int count, const int start) {
  float partial = 0.0f;
  for (int col = start; col < count; col += 1) {
    thread_local const float value = input[col];
    partial += value * value;
  }
  float scratch[32];
  const float total = combine(partial, scratch);
  return total;
}

float array_bound_effect(const float *input, int count, const int start) {
  float partial = 0.0f;
  for (int col = start; col < count; col += 1) {
    const float value = input[col];
    partial += value * value;
  }
  float scratch[(partial = 7.0f, 32)]; // Deliberate Clang VLA extension.
  const float total = combine(partial, scratch);
  return total;
}
