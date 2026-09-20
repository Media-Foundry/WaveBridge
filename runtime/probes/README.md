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

若已有完整 core wheel 中的头文件、编译器和版本化 runtime，但缺少开发链接名，
可建立项目内的 SDK linker 视图，不改动原 SDK：

```bash
python3 runtime/probes/prepare_sdk_view.py --sdk-root /path/to/_rocm_sdk_core --arch gfx1100
HIP_VISIBLE_DEVICES=0 python3 runtime/probes/probe.py --hipcc /printed/path/bin/hipcc
```

该工具只使用指定 SDK 的文件，记录 compiler/header/runtime/device-library 哈希、
实际编译参数及 wrapper。它不能代替完整 `rocm[devel]` 安装，也不保证未测试的程序
可构建。官方的开发包布局说明见 [ROCm/TheRock Python packaging](https://github.com/ROCm/TheRock/blob/main/docs/packaging/python_packaging.md)。

本机 W7900 的普通 wave32 探针已成功执行；MI250 和同卡 wave64 尚未验证。
