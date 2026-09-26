# 固定 logical32 设备对象的显式加载回放

日期：2026-09-27；实现基线 `c342c19`。

## 范围

这是一项固定历史基线的加载实验，不是任意候选执行器。入口
`experiments/module_replay.py` 只接受已封存的 code object、3×777 输入、
expected、reference 和数值协议摘要。比较器来自仓库受信任路径，而不是
执行用户传入目录中的 Python。冻结的 reference 与容限不变。

通过 HIP module API 显式加载已核对的内存字节，选择精确符号
`_Z22rms_norm_f32_logical32PKfPfif`，使用 grid=(3,1,1)、block=(256,1,1)、
动态共享内存128字节及四个参数，等待完成后复制输出。epsilon 是 binary32
`1.0e-5f`，不是 Python reference 的 binary64 字面量。

本机 GPU 0 必须匹配 AMD Radeon PRO W7900、PCI `0000:53:00.0`。
run-experiment 技能用于启动前占用检查和本机 GPU 绑定；不启动远端服务、
不计时、不调优、不执行 native64。预检及原始执行记录保存于
`artifacts/wb-module-replay-pzJL4j/`。

## 信任边界

显式提交字节、函数名及 launch 参数，比历史 host binary 的静态提取更直接
连接本次执行选择；它仍信任 HIP runtime/driver 按 API 执行，不是机器码语义
证明，也不追溯证明历史运行的动态选择。对象的 wave32 元数据与本次独立测量
实际波宽是两回事：本次没有新增设备侧波宽探针。

一次固定输入的数值通过不建立全输入域、所有浮点误差律或源目标等价。
`source_program_checked`、`actual_fp_laws_verified`、`numeric_contract_checked`
及 `deployable` 均保持 false。数值测试结果单独记录，不作部署授权。

## 执行命令

```bash
/home/husrcf/anaconda3/bin/rocm-smi \
  --showproductname --showbus --showmeminfo vram --showuse --showpids
HIP_VISIBLE_DEVICES=0 timeout 60s python3 -m experiments.module_replay \
  --code-object artifacts/binary-observation-i0z96js_/snapshot.0.hipv4-amdgcn-amd-amdhsa--gfx1100 \
  --baseline-dir artifacts/wb02-20260926T154202Z-d8e8d1 \
  --output-dir artifacts/wb-module-replay-pzJL4j/run \
  --runtime /home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/libamdhip64.so.7
```

输入与输出的形状固定为2331个binary32。设备对象摘要为
`b5c8b8abaf3972c79b7008a50116d83d7a4d1a4ae53dbe8f76b5e397ac4c9977`；
它来自上一轮保存binary快照提取，没有在本轮重新编译kernel。
预检显示GPU利用率0%、显存占用26734592字节、无KFD作业。

## 实际结果

本次执行退出码0，所有HIP调用（含清理）返回0，runtime/driver版本均为
71526333，设备名称与PCI匹配。2331个输出通过原冻结比较器，最大绝对误差
`1.1920928955078125e-7`，最大相对误差`1.1615732068736327e-7`。
9324字节输出SHA256：
`b5c96fce8dd8521bd842acd1c76337d970f73ab413950f82359cdf8a15759ddf`，
与历史GPU输出完全一致。不是新增输入域覆盖或性能结果。

原始报告 `artifacts/wb-module-replay-pzJL4j/run/report.json` 的SHA256：
`ca6b7a9a731cc8874a24b31195f281f0cdfaabf8139aa3c22c5d4d710df90a05`。
报告保存脚本及runtime摘要、命令、环境、每次API返回码和launch内容；
`replay.log`保存进程输出，`preflight.log`保存启动前设备状态。
这些本地artifacts不随git上传；本文件中的摘要与结果记录随代码提交。

CPU回归独立使用mock和临时输入，测试中临时替换pins不构成真实基线证据。
覆盖错误/缺失工件、设备不匹配、非有限输出、launch/cleanup失败、校验后
路径变化仍加载已验字节，以及底层ctypes参数地址和值。正常输出区预填NaN，
漏写不能靠未初始化内存偶然通过。

最终 `make check`：893项，66.209秒，全部通过且无跳过（设置匹配native
capture插件及AOCC编译器）；`make demo`、`git diff --check`通过。
GPT-5.6 Sol对最终脚本、测试及实机报告只读复核，无阻断问题。
