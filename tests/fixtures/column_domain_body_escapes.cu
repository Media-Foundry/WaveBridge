// Host-only CUDA parsing fixture. It is never compiled or run on a GPU.
struct dim3 {
  unsigned x, y, z;
  dim3(unsigned x_, unsigned y_ = 1, unsigned z_ = 1)
      : x(x_), y(y_), z(z_) {}
};
int cudaConfigureCall(dim3, dim3, unsigned long = 0, void * = nullptr);
constexpr int block_threads = 256;

#define COLUMN_KERNEL(NAME, BODY)                                             \
  __attribute__((global)) void NAME(float *output, int count, int seed) {     \
    const int tid = seed;                                                     \
    for (int column = tid; column < count; column += block_threads) {         \
      output[column] = 1.0f;                                                  \
      BODY                                                                    \
    }                                                                         \
  }

COLUMN_KERNEL(ordinary_columns, )
COLUMN_KERNEL(direct_columns, column += block_threads;)
COLUMN_KERNEL(static_cast_columns, static_cast<int &>(column) += block_threads;)
COLUMN_KERNEL(c_style_columns, (int &)column += block_threads;)
COLUMN_KERNEL(comma_columns, (0, column) += block_threads;)
COLUMN_KERNEL(asm_columns, asm volatile("" : "+r"(column));)

#define LAUNCHER(NAME, KERNEL)                                                \
  void NAME(float *output, int seed) {                                        \
    const int columns = input_value();                                        \
    if (columns < 1 || columns >= 1024)                                       \
      return;                                                                 \
    KERNEL<<<dim3(1), dim3(block_threads)>>>(output, columns, seed);           \
  }

int input_value();
LAUNCHER(launch_ordinary, ordinary_columns)
LAUNCHER(launch_direct, direct_columns)
LAUNCHER(launch_static_cast, static_cast_columns)
LAUNCHER(launch_c_style, c_style_columns)
LAUNCHER(launch_comma, comma_columns)
LAUNCHER(launch_asm, asm_columns)
