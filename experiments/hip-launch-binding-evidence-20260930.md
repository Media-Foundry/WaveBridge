# HIP 精确 launch 绑定（2026-09-30）

基线256b81a，当前工作分支wb03-source-ast。复用softmax_launch_native驱动，
不另写launch checker、不复用CUDA AST ID。默认cuda路径保留；显式hip路径
固定native SHA与kernel ID，所有CUDA专用host/object选点选项明确拒绝。

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_launch_native \
  --profile hip \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-launch-binding-20260930-01/report.json
```

输入SHA：`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
报告SHA：`d3b3572a29be63dc6687158d7f3f183b2ac19039d9629c1f05e1a3eeb6711124`。
输入/src/driver哈希前后稳定、结束后核对一致。报告为本地工件，不是完整公开复现包。

## 实际结果与下一个义务

同root先发现、再fresh调用launch_binding.check：

- kernel声明 `0x745c579e5490`；唯一选定launch `0x745c579e57a8`。
- configuration声明 `0x21804370`；4槽位、8个kernel实参按位置绑定。
- 选定绑定checked，但另外22个未解析位置保留；不声称全TU解析完成。
- 第二配置槽位 `0x745c579e4968` 是CXXConstructExpr，copy来源threads声明
  `0x745c57a5bfe8`，不是literal或已检查的block域。
- 第一槽位 `0x745c579e4938` 包含wb_observe_grid调用，实参也包含threads复制。
  不能删掉该调用或假设配置求值间没有效果来得到对象值保持。
- 第四槽位 `0x745c579e4818` 包含stream getter调用。

checked仅表示同AST的语法身份、声明/callee类型与位置绑定。配置槽位的API
意义、对象历史、字段值、调用顺序/效果、host可达性和实际launch均未证明。
`configuration_values_established`、`lane_family_established`、source/deploy/GPU
标记仍为false。因此不能据此把上轮getter返回域缩成[0,31]。

下一步复用对象初始化/复制检查，精确处理threads声明到配置copy的值链，
然后才是配置API与外部坐标语义的条件连接。旧CUDA对象报告不能替代HIP检查。

## 验证

3项driver回归覆盖profile/hash错配、所有CUDA选点选项拒绝、两profile各自
精确kernel身份、fresh检查unknown传播及未解析项保留。这些是mock编排fixture，
不冒充源码测试；上面的实际HIP重放独立调用生产checker，不mock。
本轮没有新采集、GPU或性能作业。CPU验收使用SDK23/AOCC17匹配插件的混合环境。
最终 `make check` 1275项、96.597秒、无跳过；日志 `/tmp/wb-hip-launch-check.log`。
`make demo`、`git diff --check`通过，Sol只读复核未发现阻断问题。
