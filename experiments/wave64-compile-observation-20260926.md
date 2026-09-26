# gfx1100 wavefront 编译观察（非 GPU 实验）

日期：2026-09-26；基线：`411c775`，分支：`wb03-source-ast`。
输入为未修改的`runtime/probes/device_probe.hip.cpp`，不是RMSNorm候选。
本机HIP 7.15.26333、AMD Clang 23.0.0git（LLVM提交
`8f497e0992fb7513f7f78a6f6b6f1056c375e961`）。

## 实际结果

| 模式 | 编译退出码 | 提取成员的 kernel 元数据波宽 | GPU 执行 |
| --- | ---: | ---: | --- |
| 默认 gfx1100 | 0 | 32 | 未执行 |
| gfx1100 + `-mwavefrontsize64` | 0 | 64 | 未执行 |

成员名：`hipv4-amdgcn-amd-amdhsa--gfx1100`。两个成员均逐SHA核对与对应
device链接临时`.out`相同，元数据解析限定`wavebridge_probe`符号。
不是host可执行程序的验收，也不证明实际设备的执行模式。

## 复现步骤

使用独立空目录分别保存两种模式，不执行生成物。以下为命令模板，路径替换为
本机绝对路径；`EXTRA_FLAG`默认模式留空，实验模式仅填`-mwavefrontsize64`。

```bash
hipcc -O0 -g --save-temps --offload-device-only --offload-arch=gfx1100 \
  EXTRA_FLAG -MD -MF /absolute/mode/inputs.d -MT wavebridge-inputs \
  -c /absolute/mode/device_probe.hip.cpp -o /absolute/mode/device_probe.o
clang-offload-bundler --list --type=o --input=/absolute/mode/device_probe.o
clang-offload-bundler --unbundle --type=o \
  --targets=hipv4-amdgcn-amd-amdhsa--gfx1100 \
  --input=/absolute/mode/device_probe.o --output=/absolute/mode/extracted.hsaco
llvm-readobj --file-headers --notes /absolute/mode/extracted.hsaco
```

实际driver命令另加`-###`保存展开记录。工具来自同一SDK：
`/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin`；
hipcc为`/home/husrcf/anaconda3/bin/hipcc`。

## 工件与失败记录

本地目录：`artifacts/wb-wave64-compile-gloEbQ/`，不随Git上传。
包含`compile_only.py`、`inspect_bundle.py`、源副本、预处理输入、bundle、
提取成员、driver trace、原始日志、工具与产物哈希。

- `report.json`：`9920f7bb140c9c00a095143e6c6aa9e02fd392f9aebf60d60a434675e18f38c4`。
- `bundle-inspection.json`：`37a41d11dcbf8cb09e20358759c63bf1a95e9e8f42f9c99ec9aecd346d8043fd`。
- 默认成员：`0ce4d28b1d16a270784e03c778289fa61e42d3d6b58357c17d0e1325e22d8b49`。
- 实验成员：`692188447625333355cce4cf6391ebe1801705138808c4972a9bb8b6547c5135`。

首次把bundle当ELF交给readobj，退出1；后续显式提取成员才成功，原失败保留。
编译器报告`-MF`未使用，没有生成请求的依赖清单，闭包仍为unknown。
预处理输入已哈希，但设备库、完整SDK闭包未因此被绑定。

## 决策边界

[HIP develop硬件文档](https://rocmdocs.amd.com/projects/HIP/en/develop/reference/hardware_features.html)
注明RDNA的实验wave64选项影响代码生成，但HIP运行时不支持。
这是查阅时develop文档的说明，不冒充本机7.15工具链实测结论。
[Clang选项参考](https://clang.llvm.org/docs/ClangCommandLineReference.html)
列出该选项，选项存在不等于运行支持。

因此没有启动GPU，不产生性能/数值结果；runtime_verified和deployable均为false。
不修改默认wave32探测协议，不用host属性或编译成功替代设备侧行为证据。
下一步继续离线语义检查；native64执行另需已确认支持的设备与运行时，不能依赖
W7900实验模式一定可用，也不能据此宣称MI250路径已验证。
