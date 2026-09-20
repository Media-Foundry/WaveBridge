# 分阶段定位与 O1 数值对照

- 日期2026-09-20，分支wb03-source-ast，基线c514b76；中文、直接commit、不push。
- 用户已授权本机W7900；按run-experiment技能再次预检，GPU0/PCI0000:53:00.0
  使用率0%、VRAM26734592字节，无KFD进程。所有设备诊断串行，未运行性能实验。
- 工件根 `artifacts/polygeist-stage-diagnostic-WR2boD/`，全部日志及独立脚本留存。

## 分阶段证据

相同3×1输入，逐个独立编译、静态检查gfx1100/wave32与无非空未定义动态符号，
host链接后确认HSACO在可执行文件中唯一嵌入，再在同一设备执行。
保持host编译O0与链接选项不变，不改数值协议。

| 源码诊断 | cgeist级别 | 三个输出 | 解释 |
| --- | --- | --- | --- |
| partial.cu，仅保留局部平方和及输出循环 | O0 | 三个0x00000100 | 累加阶段已错误 |
| warp.cu，仅再做第一阶段logical32归约 | O0 | 三个0xffffffff/NaN | 不能独立归因shuffle |
| load.cu，去累加循环，输出各行x[0] | O0 | -2, 0.046875, -1.921875 | 此小输入的基本load/store与行寻址正确 |
| constant.cu，去累加循环，输出1.25 | O0 | 1.25, 1.25, 1.25 | 此小输入的常量写入正确 |
| 原partial.cu | O1 | 4, 0.002197265625, 3.693603515625 | 三个平方和精确吻合 |

`run_stages.py`、`run_controls.py`保存每一步命令至各产物目录commands.json。
`stages.json` SHA256：`9422af59019eb8076490a2bb654706200322386fd0c39987861bb92bfcf26ffe`。
`controls.json` SHA256：`95a70ef3342575221422cd2d92feac8d8aaaf92396208f3fe77649016209f295`。
两索引包含源码/二进制/HSACO哈希、raw u32和输出。partial-o1/result.json另存对照。

`capture_intermediate.py`以原O0命令增加`--output-intermediate-gpu`并更换输出文件，
捕获优化前后设备LLVM与ISA；没有覆盖旧结果。`intermediate.stdout` SHA256：
`5e16c82cb32e2f55b354e9e43f06aa730e2f7b2c05b8d1602eb10b068aba8264`。
两份LLVM中都有正确的float累加PHI和独立的列步长256，输出仍store累加PHI。
Sol只读审计指出ISA存在重spill及先读后写的lane载体，但该控制流中的undef是否
真正造成错误仍未证明。O1同时改变多个优化与codegen选择，只能作为范围收缩证据，
不能声称已定位或修复特定spill bug，更不能归因硬件损坏。

## 完整人工 RMSNorm 的 O1 验收

`run_full_o1.py`读取wave补丁后的同一人工源码编译命令，只将cgeist的-O0改为-O1、
并更换输出路径。源码不变，仍为static-shared/OCML/OCKL人工适配版本；wrapper、
AS5 alloca、wave控制常量等兼容补丁仍在。完整命令在full-o1/commands.json。

- full-o1/embedded.hsaco SHA256：`378bd0a1687d59381528da31d7ab6af19526bb1b96c17c5959a5112f33f84e66`
- full-o1/harness SHA256：`b35d4a9dc04514d33624cf2ed89497603ffba7438bf494e229809cfc0204fee6`
- full-o1/numeric-report.json SHA256：`8b00bca120d7f58541d28328465fc0f2b48f5a63958cf42762b9574df7b442fa`

实际命令：

```
env -u ROCR_VISIBLE_DEVICES -u CUDA_VISIBLE_DEVICES HIP_VISIBLE_DEVICES=0 LD_LIBRARY_PATH=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib python artifacts/polygeist-stage-diagnostic-WR2boD/full-o1/run_numeric.py
```

按既有evidence.json的原输入哈希与冻结reference/protocol，依序执行3行×
1、31、32、33、255、256、257、777、1023列，9项均passed；每项真实设备与HIP
版本均匹配旧基线。最大绝对误差1.1920928955078125e-7，所有元素通过冻结容差。
原O0失败工件完整保留，不将记录脚本退出0冒充数值通过。

## 范围与下一步

只覆盖9个确定性输入，不是整个输入域证明、性能实验、native64适配或自动候选。
该路径明确修改了API与shared存储，不能称为未经修改的论文工件。
本轮未修改tracked实现，未重复CPU测试；设备实测不替代CPU回归。
下一步将优化级别接入正式baseline记录器及测试，固定可复现O1配方；然后回到
源码恢复/候选验证主线，不继续用O0工具链故障充当研究gap。
