// Real-Clang regression for writes which hide behind lvalue-producing syntax.
constexpr int block_threads = 256;

void ordinary_index(float *input, float *output, int tid, int count) {
  for (int column = tid; column < count; column += block_threads)
    output[column] = input[column];
}

void static_cast_alias(float *output, int tid, int count) {
  for (int column = tid; column < count; column += block_threads) {
    output[column] = 1.0f;
    static_cast<int &>(column) += block_threads;
  }
}

void c_style_alias(float *output, int tid, int count) {
  for (int column = tid; column < count; column += block_threads) {
    output[column] = 1.0f;
    (int &)column += block_threads;
  }
}

void comma_lvalue(float *output, int tid, int count) {
  for (int column = tid; column < count; column += block_threads) {
    output[column] = 1.0f;
    (0, column) += block_threads;
  }
}

void inline_asm_escape(float *output, int tid, int count) {
  for (int column = tid; column < count; column += block_threads) {
    output[column] = 1.0f;
    asm volatile("" : "+r"(column));
  }
}

#ifdef WAVEBRIDGE_CPU_WITNESS
int main() {
  float output[768] = {};
  for (int tid = 0; tid < block_threads; ++tid)
    static_cast_alias(output, tid, 768);
  int written = 0;
  for (float value : output)
    written += value != 0.0f;
  return written == 512 ? 0 : 1;
}
#endif
