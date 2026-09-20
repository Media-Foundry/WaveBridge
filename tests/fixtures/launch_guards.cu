// CPU-only Clang CUDA parsing fixture, not a GPU execution benchmark.
struct dim3 {
  unsigned x, y, z;
  dim3(unsigned x_, unsigned y_ = 1, unsigned z_ = 1)
      : x(x_), y(y_), z(z_) {}
};
int cudaConfigureCall(dim3, dim3, unsigned long = 0, void * = nullptr);
__attribute__((global)) void entry(int columns) {}
int input_value();
void escape(const int *);

void direct_launch() {
  const int rows = input_value();
  const int columns = input_value();
  if (rows < 1 || rows > 8 || columns < 1 || columns >= 1024)
    return;
  entry<<<dim3(rows), dim3(256)>>>(columns);
}

void macro_style_launch() {
  const int rows = input_value();
  const int columns = input_value();
  if (rows < 1 || rows > 8 || columns < 1 || columns >= 1024)
    return;
  do { entry<<<dim3(rows), dim3(256)>>>(columns); } while (0);
}

void ordinary_host_flow() {
  const int argc = input_value();
  if (argc != 5) return;
  const int rows = input_value();
  const int columns = input_value();
  if (rows < 1 || rows > 8 || columns < 1 || columns >= 1024)
    return;
  input_value();
  if (!input_value()) return;
  entry<<<dim3(rows), dim3(256)>>>(columns);
}

void escaped_launch() {
  const int rows = input_value();
  if (rows < 1 || rows > 8) return;
  escape(&rows);
  entry<<<dim3(rows), dim3(256)>>>(1);
}

void bypassed_guard() {
  const int rows = input_value();
  goto launch;
  if (rows < 1 || rows > 8) return;
launch:
  entry<<<dim3(rows), dim3(256)>>>(1);
}
