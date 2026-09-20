# 交接：静态 shared 的真实后端对照

- 日期/分支/基线：2026-09-20，wb03-source-ast，ba8dfc2；中文、直接commit、无PR/push。
- 输入：artifacts/polygeist-static-shared-huVSt0/adapter.cu，hash
  `f29dd62b5c44e2330e4376ea306c5f36f5bb195612fac0bd98e574ed7489c739`。
  再次diff确认仅extern shared[]改为static-size shared[32]，源码launch不变。
- 工具/参数/环境沿用首个工件交接：cgeist hash ef5fb79a，gfx1100、sm_70、
  backend-view-01、CUDA11.8/GCC11 includes、function=*、O0、不启用cuda-lower。
  `LD_LIBRARY_PATH=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib`，
  `PYTHONPATH=src`；命令与日志在报告，环境由本记录补充。
- GPU MLIR：artifacts/polygeist-frontend-yl3m9_6r/report.json，退出0，hash
  `7368a49578cc8fcf58e64b232d534a76f1e20ddf2a806bf6937f12a0b6d3b526`；
  output.mlir hash `4ff001e381e5b930f4fb96c2c9e574d9f6fd5a71f9f4b8607ba0549c51d49ae4`。
  实际shared为memref<32xf32,3>；两个外部shuffle call、host launch存在；无alternatives。
- LLVM/HSACO：artifacts/polygeist-frontend-qfsqc8w6/report.json，退出0，hash
  `f0e163c8a10bfb92ca543a796e2a72fb7b04ce4b166da97b066d438cd8b546bf`；
  output.ll hash `426e597b50eb028980a801a3f019b73e890001ce4b87a5ac2f2f29e6a75d21da`。
- 复用上轮诊断解码脚本，提取embedded.hsaco 7928字节，hash
  `874434b92aa5341c2174635413e46c9e2e65da95363a8ba1d0e35329aed1dab4`。
  SDK llvm-readobj --notes --dyn-symbols结果在readobj.log，hash
  `d79f836bf64962b5b1d67ff7d2a8beca20e23adcf8747e274e226bb4e8c20632`。
- kernel96991018788144的固定共享空间128字节、wavefront_size32、target gfx1100；
  仍有动态未定义__nvvm_shfl_sync_bfly_f32、__nv_rsqrtf；host LLVM第182行smem=0。
- 结论：容量和符号缺口可分别观察。容量修正不解决通信/数学映射；产物未放行。
  静态数组副本不是自动候选或等资源基线；元数据不证明物理执行波宽。
- 未执行：GPU加载/数值/性能、完整host链接；本轮无产品代码变更，文档做diff检查。
- 下一步：核查固定版已有映射入口及最小普通lowering对照，避免把实现缺项当研究创新。
  源码→自动关系→候选→GPU闭环、G1、CKTI能力比较均未完成。
