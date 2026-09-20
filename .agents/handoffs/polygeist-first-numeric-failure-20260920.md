# Polygeist 人工基线首次 W7900 数值验收

- 日期：2026-09-20；分支 wb03-source-ast，基线 b6f3697。
- 用户明确授权继续使用本机 W7900；中文、直接本地commit，无PR/push。
- 按 run-experiment 技能执行本机环境确认、设备占用预检和有限运行；未发外部通知。

## 预检及新工件

`rocm-smi --showproductname --showbus --showmeminfo vram --showuse --showpids`
确认GPU0为W7900/gfx1100/PCI 0000:53:00.0，使用率0%、VRAM使用26734592字节，
没有KFD进程。日志 `artifacts/polygeist-host-wave-fixed-EtryQy/preflight.log`，SHA256
`204f7edad47e0a4cb25f20ec283e51f6f092cf82a2d2daba09a80a8d5547cf75`。

固定LLVM16 clang `-c -x ir -O0 -fPIC` 编译上一轮gfx1100 output.ll，
AOCC clang++ `-std=c++17 -D__HIP_PLATFORM_AMD__`，使用SDK include/lib/rpath、
`-l:libamdhip64.so.7`，将现有polygeist_harness.cpp与generated.o链接成功。
结果及compile/link.log在 `artifacts/polygeist-host-wave-fixed-EtryQy/`。
执行前逐字节确认新HSACO在可执行文件中唯一出现，未沿用旧harness。

- HSACO：`456892620a62f98cbcec528a3a17ce1bba127780422165d639c4f70b52fb7196`
- harness：`c0a73010128c0245198503fcde771936b66a4f3aa6016909d1d46cdbfec122e9`

## 实际执行与失败

```
env -u ROCR_VISIBLE_DEVICES -u CUDA_VISIBLE_DEVICES HIP_VISIBLE_DEVICES=0 LD_LIBRARY_PATH=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib python artifacts/polygeist-host-wave-fixed-EtryQy/run_numeric.py
```

脚本绑定已有9形状索引、输入哈希、冻结protocol和独立reference，单进程超时30秒，
遇到首个失败停止。脚本自身退出0只表示记录完成，内部报告status为failed。
此次只执行3×1：设备身份、HIP版本与既有基线一致，程序返回0，但输出3个NaN。
reference.compare给出numeric_mismatch/nonfinite_or_outside_tolerance。
未执行其余8形状，未修改容差，未做计时实验；命令耗时不是kernel性能。

完整记录：`artifacts/polygeist-host-wave-fixed-EtryQy/numeric-report.json`，SHA256
`57a1710c6f5f7decc013f46bdb0879177e89452dac862497947e56ae949dfbce`。
注意：人工静态shared128替换原dynamic shared128；生成launch仍为dynamic0，
必须作为基线改写记录，不能声称原launch逐字段不变。

## 分阶段诊断

独立目录 `artifacts/polygeist-total-diagnostic-v1JZNg/` 保存源码、compile.py、run.py、
编译/链接日志、完整执行记录和输出。相对原人工诊断源码只把
`dst[col] = scale * x[col]` 改为 `dst[col] = total`，不改变冻结协议，也不把此程序
当RMSNorm正确候选。重新编译、确认gfx1100/wave32/shared128及无非空未定义符号，
host链接后确认HSACO唯一嵌入，再用相同设备和3×1输入运行，仍得到3个NaN。

- 诊断源码：`6d737c480c02d21bc62c14bda422a71d82a3f8a30e7c64780c7b83f106bb2ff4`
- HSACO：`621905862e9c13aca006df89ef7c42db32c772bd33d54fcb13fc4b3ec1dcc3c7`
- harness：`b70e2c18a4c91aa3fbe5b67869f0c699291e550d42ead9e39b8ea787d6bdd333`
- execution.json：`602a5d09a3f7ce624c68939b6a8e73e6820bfbf6b596396f0e7132a01f2013ac`

该对照提示继续检查归约以前的路径，但源码变化也可能改变优化，不能凭此确定根因。
下一步输出局部partial/第一阶段shuffle结果，定位局部load、位搬运或共享阶段；
保留所有失败工件，不扩大形状/调优。不把本地兼容实现错误当作论文方法局限。

Sol只读审计另确认当前工具入口不能直接注入wave补丁mixed/unknown/type负例；
需要独立真实AMDGPU TargetMachine测试driver。双目标正向编译不覆盖这些拒绝分支。
本轮未改tracked实现，未重复CPU测试；上轮284项通过不能证明设备正确。
