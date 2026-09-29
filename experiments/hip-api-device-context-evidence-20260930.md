# ABI 探针与原 HIP 编译上下文对照

基线 `e511771`，分支 `wb03-source-ast`。没有程序或 GPU 执行。

## 实际发现的上下文差异

原 native 工件 `artifacts/wb-hip-native-20260927-01/native.json` 的命令使用
hipcc、C++17、O2、`--offload-device-only`、`WB_COMPILED_COOP_WIDTH=32` 和原
源码目录；payload 的 ast_target_triple 是 `amdgcn-amd-amdhsa`。上一轮独立
host 探针的 dry-run triple 是 `x86_64-unknown-linux-gnu`。因此不能直接把
host 探针结果当成原 AST 的类型/ABI 事实。

本轮增加可选 `--hip-context-source`，用明确写在 driver 中的 pilot 配方
重跑 device-only 编译，并强制包含原始 harness。不会执行工件中读出的命令。
context 文件在采集前后哈希核对，且同次依赖清单必须有唯一匹配项。
context 模式由 hipcc 选择 SDK；`--include` 仅用于旧 standalone host 模式，
实际命令完整记录。输入文件路径无效会在编译前报错，不签发 observed。

## 命令

```bash
PYTHONPATH=src:. python -m experiments.hip_api_abi_probe \
  --compiler artifacts/toolchains/sdk-view-sx4rmd37/bin/hipcc \
  --include artifacts/toolchains/sdk-view-sx4rmd37/include \
  --hip-context-source artifacts/wb-softmax-hip-pilot-20260927-10/pytorch-softmax-hip.hip.cpp \
  --output artifacts/wb-hip-api-device-context-20260930-02/report.json
```

02 报告 SHA256：`9631a36b59af3ef3edf0b078d679c72f4850d9faf6832d6f1da6ea06a1d328c4`。
context 源码 SHA256：`fcfa6606452f25ce85508267bffff7ba743148ffef0b600e05b9b54f8bac3cc0`。
hipcc wrapper SHA256：`c532a4908b542bfebaebddb0831dd93213a1cb98cbda57d168271e5d31a3e028`。
01 是首次成功采集；之后完善CLI说明和测试，按最终driver重新产生02，未覆盖01。

## 对照结果

新 dry-run 计划为 `amdgcn-amd-amdhsa / gfx1100`。新清单335项，旧清单334项；
按 resolved_path 比对，旧334项全部存在且SHA256相同，只有探针cpp文件新增。
这说明所观察依赖内容一致，不证明冻结输入闭包、宏环境或实际cc1进程一致。

观测值与前轮host探针相同：int/status/underlying均32位、底层unsigned int、
success转int为0、Tbd转int为1055、unsigned最大值转int为-1的单点结果为true。
它们是两次具体编译的观察，不是一般转换规律或运行时枚举值域。

## 尚未建立什么

新主输入是探针文件，原harness通过`-include`引入；这改变了include level和
base file，且没有使用原native插件。新工件没有宣称整个原TU语义完全相同，
`original_kernel_TU_ABI_binding=false`始终保留。旧AST的ID不能跨编译复用。
需要的下一步是同次原TU原生类型观测或另一条明确的上下文关联证据，而不是
只因依赖/观测值一致就解除API/ABI义务。

## 验证

6项parser/driver fixture回归通过，覆盖显式配方、context依赖正确/缺失/错hash、
trace失败、字段类别及ID校验；fixture不当作真实SDK结果。Sol只读复核无阻断，
make demo和git diff --check通过。完整CPU回归以补记为准。

补记：完整1327项CPU回归98.606秒通过、无跳过，日志
`/tmp/wb-api-device-context-check.log`。环境沿用SDK Clang23相关专项和匹配插件、
AOCC Clang17旧native capture和匹配插件、PATH clang++普通fixture。
