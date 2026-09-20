// Compiler-only regression; external reduction has no assumed semantics.
float combine(float, float *);
constexpr int step = 256;
float entry(const float *input, int count, int tid) {
  const int start = tid;
  input += 0;
  float partial = 0.0f;
  for (int col = start; col < count; col += step) {
    const float value = input[col];
    partial += value * value;
  }
  float scratch[32];
  const float total = combine(partial, scratch);
  return total;
}
float wrong_index(const float *input, int count, int tid) {
  float partial = 0.0f;
  for (int col = tid; col < count; col += step) {
    const float value = input[tid];
    partial += value * value;
  }
  float scratch[32];
  const float total = combine(partial, scratch);
  return total;
}
float modified(const float *input, int count, int tid) {
  float partial = 0.0f;
  for (int col = tid; col < count; col += step) {
    const float value = input[col];
    partial += value * value;
  }
  partial += 1.0f;
  float scratch[32];
  const float total = combine(partial, scratch);
  return total;
}
