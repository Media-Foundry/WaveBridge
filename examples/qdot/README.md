# 量化点积参考案例

数学对象为 `y[row] = Σ q[row,j] * scale[row,j // 32] * x[j]`。采用无界整数，固定 5 行、65 列，每块 128 个线程。

- `source.json`：32 lane/行，2 个块。
- `logical64.json`：64 lane/行，3 个块，量化分组仍为 32；预期 `checked`。
- `wrong_quant64.json`：把量化分组也改成 64；预期 `rejected`。

这些文件是人工提供的模型，不是 HIP 源文件、源码恢复结果或 GPU baseline。`logical64` 不声明实际物理 wave64。5 行用来暴露 launch 更新遗漏，65 列用来覆盖量化分组和协作宽度的边界。
