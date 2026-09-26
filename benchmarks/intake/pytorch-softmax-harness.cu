// WaveBridge analysis-only instantiation harness. No GPU execution or linking.
// The selected upstream header and its kernel/helpers are not modified.
#include <c10/cuda/CUDAStream.h>
#include <c10/cuda/CUDAException.h>
// Exact return/parameter signature from PyTorch CUDAContextLight.h.
// No definition or semantic replacement for this external query is supplied.
namespace at::cuda { int warp_size(); }
#include <ATen/native/cuda/PersistentSoftmax.cuh>

void instantiate_pytorch_softmax(float* output, const float* input,
                                 int rows, int columns) {
    dispatch_softmax_forward<float, float, float, false, false>(
        output, input, columns, columns, rows);
}
