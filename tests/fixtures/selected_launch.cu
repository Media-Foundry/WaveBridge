// A real unresolved dependent launch does not erase a distinct exact site.
#include "lambda_launch.cu"

template <typename Kernel>
void deferred_launch(Kernel kernel, int* output) {
  kernel<<<dim3(1), dim3(32)>>>(output);
}

void another_exact_launch(int* output) {
  target<<<dim3(2), dim3(64)>>>(output);
}
