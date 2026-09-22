// Host-only syntax fixture: duplicate AST appearances are not executions.
struct dim3 {
  unsigned x, y, z;
  dim3(unsigned a, unsigned b = 1, unsigned c = 1) : x(a), y(b), z(c) {}
};
int cudaConfigureCall(dim3, dim3, unsigned long = 0, void* = nullptr);
__attribute__((global)) void target(int* output) { output[0] = 1; }
void launch_in_lambda(int* output) {
  auto invoke = [&] { target<<<dim3(1), dim3(32)>>>(output); };
  invoke();
}
