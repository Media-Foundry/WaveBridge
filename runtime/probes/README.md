# WB-01 HIP 设备探测器

该探测器编译并执行一个 64-thread HIP kernel，分别记录 host 设备属性、device-side
`warpSize`、`ballot` 和 `shuffle` 的原始结果，再尝试从同次编译通过 `--save-temps`
保存的 AMDGPU code object 中读取与探针 kernel 绑定的 wave 元数据。可执行文件的
`strings` 结果只作诊断，不签发结论。普通路径不强制 wave32 或 wave64，也不会把
width 参数当作物理波宽。

```bash
python3 runtime/probes/probe.py
python3 runtime/probes/probe.py --timeout 60 --output-base artifacts
```

每次运行创建不覆盖的 `artifacts/wb01-<id>/`，其中有 HIP 源码和 runner 副本、二进制
（编译成功时）和 `report.json`。报告保存副本 SHA-256、完整命令、stdout、stderr、
超时和分阶段状态，因此未提交工作树中的实际探针也可追溯。

退出码为：`0` 表示运行证据与编译元数据一致；`1` 表示编译/执行/语义冲突；`2`
表示工具缺失、无设备、超时或元数据未建立等未知状态。仅有运行时探针一致但未能从
编译产物建立 wave 元数据时，整体仍为 `unknown`。
