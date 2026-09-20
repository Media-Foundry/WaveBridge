# 优化级别接入正式记录器

- 日期2026-09-20；分支wb03-source-ast，基线369cc15；中文、直接commit、不push。
- `experiments/baselines/polygeist_frontend.py`增加API `optimization_level`及CLI
  `--optimization-level`，严格整数0–3，默认0。拒绝bool/float/string/越界值，
  在目录创建及进程调用前失败。报告新字段、pipeline标签及-O参数绑定同一值。
- 不改变ROCm前提、可见设备掩码、禁止cuda_lower、未验证状态与部署边界。
- 测试覆盖所有合法级别、拒绝类型/范围、CLI默认/显式传参、两阶段ROCm O1命令
  及隔离；均为CPU编排测试，不声称O2/O3真实工具或设备能力。
- `make check`实际287项通过；日志 `artifacts/polygeist-o1-recorder-VgmeJk/cpu-checks.log`。
- 正式API对原人工OCML/OCKL/static-shared源码实际编译：
  `LD_LIBRARY_PATH=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib PYTHONPATH=src python artifacts/polygeist-o1-recorder-VgmeJk/compile.py`。
  同一patched cgeist、gfx1100、emit_llvm=True，optimization_level=1。
- 报告 `artifacts/polygeist-o1-recorder-VgmeJk/polygeist-frontend-nwf0fcq6/report.json`，
  SHA256 `f06b548fd628058df157c6833c3d64303461ca1b2014e6c89d5219871a5a49a7`，
  状态emitted_unverified_ir，pipeline=cgeist_O1_rocm_llvm，optimization_level=1。
- 本轮没有GPU执行。先前9形状结果仅绑定原O1工件，不能自动转移到本次产物。
- 下一步回到源码恢复/独立目标检查：先明确首例仍依赖外部语义的缺口，选择一个
  能直接服务候选生成的受限关系；不把完成兼容基线当作研究门槛G1已通过。
