# HIP host 尺寸关系重放（2026-09-30）

基线486c0e7，分支wb03-source-ast。扩展既有launch驱动，不修改生产checker。
从同次fresh launch slot1选择对象，在对象原始构造实参0/1中按精确声明ID
选出变量，验证同一owner及唯一赋值候选，再分别调用四个integer_selection
入口。不按名字填值、不读取人工域；候选形状本身不签发关系通过。

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_launch_native \
  --profile hip --host-dimensions \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-host-dimensions-20260930-01/report.json
```

输入SHA `46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`；
报告SHA `44168448dc6e9fe329d3e72b100df764b3d5444660b90c6f85197020f2016dce`。
输入/src/driver前后及结束后复核一致。原始大工件仅在本地artifacts。

## 选点与结果

- owner `0x22508c60`，对象 `0x745c57a5bfe8`，构造 `0x745c57a5c138`。
- 目标语句 `0x745c57a5c178`，更新 `0x745c57a5b9d0`。
- minimum目标 `0x745c57a5b7a0`，另一操作数 `0x745c57a5b680`。
- quotient声明 `0x745c57a5bbe0`。

四个fresh子检查均条件checked：minimum状态转移、到目标语句首次入口的
保持、常量128除以该minimum的向零取整商关系、商值到同一语句入口保持。
128来自源码常量求值，不是输入域。除法非零前提尚未解除。

诊断父状态observed只表示已运行，子结果单独保留，永不聚合成源码通过。
没有建立操作数数值域、构造实参IntegralCast值保持、位置到字段映射、
目标语句内求值效果、对象值历史或launch域。语句入口保持不覆盖语句内部。
不能推出block=(32,4,1)、lane[0,31]、完整源码/GPU正确性或部署结论。

下一步检查minimum操作数的初始化：warp-size helper返回与next-power-of-two
的host计算，并追踪到更新点；然后再连接分母安全、构造转换及字段映射。
当前没有将这些关系手动转换成selection_domain_missing所需的小域。

## 回归

driver定向6项通过：原profile隔离、fresh对象绑定，以及变量改名后按身份
选点、重复赋值拒绝、四次fresh调用参数与unknown原样传播。属于mock编排
fixture，不计源码覆盖；上述HIP重放独立运行真实checker。
Sol只读复核无阻断，强调实参位置不是字段语义。无GPU、新编译或性能作业。
最终make check：1280项、97.010秒、无跳过，日志 `/tmp/wb-host-dimensions-check.log`。
SDK23/AOCC17匹配插件混合验收（visibility另用SDK23），非全量SDK23。
make demo、git diff --check通过。
