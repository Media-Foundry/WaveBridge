// Real-Clang regression for writes which hide behind lvalue-producing syntax.
constexpr int block_threads = 256;
using UsingRef = int &;
typedef int &TypedefRef;
using NestedRefBase = int &;
using NestedRef = NestedRefBase;
using Value = int;

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

void using_ref_alias(float *output, int tid, int count) {
  for (int column = tid; column < count; column += block_threads) {
    output[column] = 1.0f;
    UsingRef alias = column;
    alias += block_threads;
  }
}

void typedef_ref_alias(float *output, int tid, int count) {
  for (int column = tid; column < count; column += block_threads) {
    output[column] = 1.0f;
    TypedefRef alias = column;
    alias += block_threads;
  }
}

void nested_ref_alias(float *output, int tid, int count) {
  for (int column = tid; column < count; column += block_threads) {
    output[column] = 1.0f;
    NestedRef alias = column;
    alias += block_threads;
  }
}

void value_alias(float *output, int tid, int count) {
  for (int column = tid; column < count; column += block_threads) {
    output[column] = 1.0f;
    Value alias = column;
    alias += block_threads;
  }
}

void static_induction(float *output, int tid, int count) {
  for (static int column = tid; column < count; column += block_threads)
    output[column] = 1.0f;
}

void thread_local_induction(float *output, int tid, int count) {
  for (thread_local int column = tid; column < count; column += block_threads)
    output[column] = 1.0f;
}

#ifdef WAVEBRIDGE_CPU_WITNESS
int main() {
  float output[768] = {};
  for (int tid = 0; tid < block_threads; ++tid)
    static_cast_alias(output, tid, 768);
  int written = 0;
  for (float value : output)
    written += value != 0.0f;
  float static_output[768] = {};
  float thread_local_output[768] = {};
  float using_ref_output[768] = {};
  float typedef_ref_output[768] = {};
  float nested_ref_output[768] = {};
  float value_output[768] = {};
  for (int tid = 0; tid < block_threads; ++tid) {
    static_induction(static_output, tid, 768);
    thread_local_induction(thread_local_output, tid, 768);
    using_ref_alias(using_ref_output, tid, 768);
    typedef_ref_alias(typedef_ref_output, tid, 768);
    nested_ref_alias(nested_ref_output, tid, 768);
    value_alias(value_output, tid, 768);
  }
  int static_written = 0;
  int thread_local_written = 0;
  int using_ref_written = 0;
  int typedef_ref_written = 0;
  int nested_ref_written = 0;
  int value_written = 0;
  for (int index = 0; index < 768; ++index) {
    static_written += static_output[index] != 0.0f;
    thread_local_written += thread_local_output[index] != 0.0f;
    using_ref_written += using_ref_output[index] != 0.0f;
    typedef_ref_written += typedef_ref_output[index] != 0.0f;
    nested_ref_written += nested_ref_output[index] != 0.0f;
    value_written += value_output[index] != 0.0f;
  }
  return written == 512 && static_written == 3 && thread_local_written == 3 &&
                 using_ref_written == 512 && typedef_ref_written == 512 &&
                 nested_ref_written == 512 && value_written == 768
             ? 0
             : 1;
}
#endif
