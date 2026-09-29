# Host 入口到幂次初始化的组合检查

基线 `1597497`，工作分支 `wb03-source-ast`，不运行 GPU。

## 本轮解除的局部义务

此前 `parameter_entry` 与 `initialized_shift` 只是并列报告：前者到声明入口，
后者假设实参读取点的值。本轮在 `check_initialized_shift` 增加显式
`entry_function_id` 选项，在同一次调用中 fresh 检查：

1. 同一个 plain-int 参数，从选定函数入口保持到指数声明首次入口；
2. 指数的完整 initializer 只有直接函数 designator 和一个同参数的普通读取，
   不允许默认实参、重载转换、自增、逗号副作用或额外实参；
3. 对精确 callee 定义检查幂次循环，以传入域求出指数域；
4. 指数声明与下一条移位声明紧邻，移位只读取同一个指数。

新报告 `argument_domain_derived_from_entry=true` 只在全部检查通过后建立。
它解除的是“还需另行假设调用读取点域”的义务；入口域和链接解析仍为外部
前提。`entry_domain_verified=false`、`argument_domain_verified=false` 保留，
后者表示并未验证真实运行时输入，而不是否认前者所述条件推导。
无该选项时保留旧的 at-read 假设路径；不把它静默升级为入口关系。

新路径结论限于第一次到达这对初始化时的结果；不是所有再次进入、后续值
历史、设备 API 宽度、线程坐标或可部署候选的保证。

## 重放命令

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_launch_native \
  --profile hip \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-entry-shift-20260930-01/report.json \
  --host-dimensions --power-input-domain 65 128
```

固定输入SHA256：`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
驱动从现有 fresh 绑定自动取得 host owner，新增 `entry_to_shift_check`，不接收
旧的成功报告。旧并列诊断保留，外层运行时 `call_domain_established` 仍为false。

## 验收边界

13项真实Clang power测试通过。新增正常入口/带分支入口正例，以及入口修改、
实参自增、跨声明修改、错误owner与超出有限域预算的拒绝。
特别保留一项对照：入口修改后，在“调用读取点另给域”的旧路径上仍可条件
checked，而新的入口组合必须unknown。两种保证没有混为一谈。

本轮不建立真实运行时输入协议、不证明机器码，也没有GPU数值或性能结果。
历史pilot协议只包含列数65和128；连续区间[65,128]是本次静态条件检查域，
不是64种GPU尺寸都已执行。不能用该区间取代历史原始案例记录。
下一步应接入冻结输入协议与设备API宽度证据，再检查power和width到minimum
更新的历史，不能直接把[128,128]填成已验证launch配置。

## 实际验收结果

报告SHA256：`e2953d96601b8123aedd8a3c034009f45985c1d811f5a3c6c50c331d84610155`。
输入/实现/驱动哈希稳定，`inputs_unchanged=true`。新组合入口checked，入口
保持及helper子检查均checked；`argument_domain_derived_from_entry=true`，
`initializer_prefix_preserves_parameter=true`，初始化结果域[128,128]。
真实入口域/实参域verified标记仍false，host owner为`0x22508c60`。

完整`make check`：1298项，101.301秒，无跳过。日志
`/tmp/wb-entry-shift-check.log`；沿用SDK23 visibility/unary/using及AOCC17
native插件显式配置。定向真实Clang13项、`make demo`、`git diff --check`
通过，Sol只读复核无阻断。重放期间未修改生产源码或驱动。
