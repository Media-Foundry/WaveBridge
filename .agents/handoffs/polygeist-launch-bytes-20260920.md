# 交接：动态共享 launch 信息与波宽前提

- 日期/分支/基线：2026-09-20，wb03-source-ast，de1b1ce；中文回复，直接commit。
- 实验：原host adapter只改`32 * sizeof(float)`为`64 * sizeof(float)`，
  不改kernel、block、grid、stream或数值协议；仅诊断资源信息保留，不是优化候选。
- 诊断源码：`artifacts/polygeist-launch-bytes-hpsYXD/adapter.cu`，SHA256
  `ca12e19c265cf8a064643f70a399236cdd2f1239a175a58a3cf24bb2f5bdae32`。
- 运行：`PYTHONPATH=src python experiments/baselines/polygeist_frontend.py`，
  同原报告`artifacts/polygeist-frontend-01247e7_/report.json`的固定cgeist、
  CUDA11.8/GCC11头、sm_70、resource-dir、默认function=*与O0；完整命令在新报告。
- 新报告：`artifacts/polygeist-frontend-h0mp_x8e/report.json`，SHA256
  `c2032fba121524aef2ea0a4400aa33640b532136e872ae01601fe50978af83c5`；
  cgeist退出0，仍有shuffle builtin警告，状态emitted_unverified_ir。
- `cmp`原/新output.mlir无差异，两者SHA256均为
  `7a4bf9955897efc44f4111a77f2121d3e86ba5b05004d9369743a8d0b6555196`。
- 固定Polygeist源码`tools/cgeist/Lib/CGCall.cc:336-341,1874-1879`：
  CUDAKernelCallExpr读取config参数0、1、3，构造LaunchOp时直接传动态共享大小nullptr。
  该文件SHA256为`975c0d7cbb99ddaf6913c0281d77dfc884a97f7986cfb5695bdeb323b2dddf90`，
  original与patched worktree逐字节相同。MLIR GPUDialect.cpp:413-438只在非空时添加operand。
- 范围：证明此输入/固定版本前端路径没有保留请求字节数。增加未使用的共享空间
  不一定改变数学输出；这不是数值反例，不说明所有Polygeist路径失败，不证明新算法必要。
  需与已发现的共享数组容量fallback分别记录；下一步仍是实际ROCm后端尝试。
- 子代理只读审计：SerializeToHsaco.cpp:300-315的wave64库控制常量不是机器波宽。
  driver.cc:1038-1043传gfx1100与空features；固定LLVM GFX11默认wave32。
  有库条件折叠与codegen不一致风险，但是否影响本例须核对最终保留的调用闭包。
  ABI400与LLVM16默认code-object v4一致，HIP7接受性尚未实测。
- 待建立：成功序列化、绑定kernel/hash的HSACO `.wavefront_size`及descriptor、
  实际设备身份/运行波宽。不得用硬编码或metadata独立证明物理执行。
- 验证边界：本轮是实际前端诊断及源码审计，无新GPU运行；未修改编译器或重启构建。
  完整后端沿用session29377。未push，未创建PR。
