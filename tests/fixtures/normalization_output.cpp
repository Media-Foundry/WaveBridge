// CPU compilation fixture only. External functions carry no numeric guarantee.
float reduce_partial(float, float *);
float inverse_root(float);
constexpr int step = 256;
constexpr int other_step = 128;

void entry(const float *input, float *output, int count, int tid, float epsilon) {
  const int start = tid;
  input += 0;
  output += 0;
  float partial = 0.0f;
  for (int col = start; col < count; col += step) {
    const float value = input[col];
    partial += value * value;
  }
  float scratch[32];
  const float total = reduce_partial(partial, scratch);
  const float scale = inverse_root(total / count + epsilon);
  for (int col = start; col < count; col += step)
    output[col] = scale * input[col];
}

void wrong_column(const float *input, float *output, int count, int tid, float epsilon) {
  float partial = 0.0f;
  for (int col = tid; col < count; col += step) {
    const float value = input[col];
    partial += value * value;
  }
  float scratch[32];
  const float total = reduce_partial(partial, scratch);
  const float scale = inverse_root(total / count + epsilon);
  for (int col = tid; col < count; col += step)
    output[tid] = scale * input[col];
}

void wrong_stride(const float *input, float *output, int count, int tid, float epsilon) {
  float partial = 0.0f;
  for (int col = tid; col < count; col += step) {
    const float value = input[col];
    partial += value * value;
  }
  float scratch[32];
  const float total = reduce_partial(partial, scratch);
  const float scale = inverse_root(total / count + epsilon);
  for (int col = tid; col < count; col += other_step)
    output[col] = scale * input[col];
}
