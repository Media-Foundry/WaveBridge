# Polygeist 设备库波宽修正

- 日期：2026-09-20；分支 `wb03-source-ast`，基线 `32262f1`。
- 按用户要求中文交接、直接本地 commit；不创建 PR、不 push。
- GPT-5.6 Sol 子代理实现最小 serializer 补丁，主代理审查、构建、静态复测。

## 改动与边界

`experiments/baselines/patches/rocm-device-wave.patch` 在优化/常量折叠前，
从 TargetMachine 对每个已定义函数给出的 subtarget 读取 wave32/wave64 特性。
仅当设备库 global 存在时启用，要求各函数唯一选择且全模块一致，再设置
`__oclc_wavefrontsize64`。未知、混合、无定义或非整数 global 均明确报错。
没有按芯片名猜测波宽，没有改 CLI、translation 或库链接流程。

这是固定版 Polygeist 的显式兼容补丁，不是原论文工件，也不是自动关系恢复。
输入仍为人工 static-shared + OCML + OCKL logical32 诊断副本：
`artifacts/polygeist-ockl-shuffle-YshEjS/adapter.cu`，SHA256
`87aab91bf2bdfea34b3eb762dc43bc37a389954af2063a82d9d92a07767bb1bb`。

## 实际验证

1. `cmake --build artifacts/toolchains/polygeist-rocm-build-02 --target cgeist --parallel 8`
   三任务增量构建成功，日志 `artifacts/polygeist-wave-regression-bSFKE3/build.log`。
2. `LD_LIBRARY_PATH=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib PYTHONPATH=src python artifacts/polygeist-wave-regression-bSFKE3/run_pair.py`
   从前轮 report 复用工具/include/resource/ROCm 路径，仅分别指定 gfx1100/gfx90a。
   两报告均为 `emitted_unverified_ir`，不是部署通过。
3. 每个输出目录运行 `python extract_binary.py`，从唯一 LLVM global 解码 HSACO；
   使用 `/opt/rocm/core-10.0/lib/llvm/bin/llvm-readobj --notes --dyn-symbols`、
   `llvm-objdump --disassemble --mcpu=<target>`、`llvm-objdump -s -j .rodata` 静态读取。
   完整日志保存在各目录的 readobj.log、disassembly.log、rodata.log。
4. `make check`：284项CPU测试通过。这不覆盖外部编译器补丁的所有错误分支。

工件根：`artifacts/polygeist-wave-regression-bSFKE3/`。

| 目标 / 子目录 | metadata | 地址0x7c8的库常量 | lane计数指令 | 固定shared / private字节 |
| --- | --- | --- | --- | --- |
| gfx1100 / polygeist-frontend-b6__c5bb | wave32 | 0 | mbcnt_lo | 128 / 16560 |
| gfx90a / polygeist-frontend-n90654ex | wave64 | 1 | mbcnt_lo + mbcnt_hi | 128 / 16400 |

两者均保留 ds_bpermute，动态符号表仅空符号为 Undefined。
gfx90a 的逻辑协作仍为32，不是 logical64 重分工或 MI250 实机实验。

SHA256：

- patch：`69a98b98a8a28b5fef6cf0c28ff44319a83d552605f289fa378677a81e8348b8`
- 新 cgeist：`63af9abd01e12196439aeae5f81d459e47387d093a01bb1ac02959a30fb2cc40`
- gfx1100 report：`635146b498c895f65fdc5f55a9a5dd5233e352c608626a76bbf6796e464cd4cd`
- gfx1100 HSACO：`456892620a62f98cbcec528a3a17ce1bba127780422165d639c4f70b52fb7196`
- gfx90a report：`bc318fd78499eb56c0bbcb8d8b0240b5bc74fe2537167a998a597f28afc029f1`
- gfx90a HSACO：`d33069e846a79b513258fc73cc2a231211dcc46a3fd92713b0ab4cfc0c727f95`

旧 cgeist 与 serializer 保存于 `artifacts/toolchains/polygeist-before-wave-Kdtpn5/`。
既有 alloca、wrapper 和设备库补丁仍为构建前提，见前序交接。

## 未验证及下一步

未运行GPU、未做数值/性能测试；未对 mixed/unknown/global类型错误分支注入运行测试。
仅从 metadata、常量和反汇编建立配置一致性，不验证最终机器码等价。
下一步：重新链接 gfx1100 新工件，确认 W7900 执行环境后按冻结协议做数值验收。
旧 harness 绑定旧工件，不可复用为已更新的可执行文件。
