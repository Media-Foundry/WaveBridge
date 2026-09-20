// Structural fixture; external coordinates have no assumed GPU semantics.
int row_value();
int lane_value();
float combine(float, float *);
float inverse_root(float);
constexpr int step = 256;

void entry(const float *input, float *output, int count, float epsilon) {
  const int row = row_value();
  const int start = lane_value();
  input += static_cast<long long>(row) * count;
  output += static_cast<long long>(row) * count;
  float partial = 0.0f;
  for (int col = start; col < count; col += step) {
    const float value = input[col];
    partial += value * value;
  }
  float scratch[32];
  const float total = combine(partial, scratch);
  const float scale = inverse_root(total / count + epsilon);
  for (int col = start; col < count; col += step)
    output[col] = scale * input[col];
}

void wrong_row(const float *input, float *output, int count, float epsilon) {
  const int row = row_value();
  const int start = lane_value();
  input += static_cast<long long>(row) * count;
  output += static_cast<long long>(start) * count;
  float partial = 0.0f;
  for (int col = start; col < count; col += step) {
    const float value = input[col];
    partial += value * value;
  }
  float scratch[32];
  const float total = combine(partial, scratch);
  const float scale = inverse_root(total / count + epsilon);
  for (int col = start; col < count; col += step)
    output[col] = scale * input[col];
}
