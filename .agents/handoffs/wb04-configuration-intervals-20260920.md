# 配置字段区间检查交接

- 日期、分支和基线：2026-09-20，`wb03-source-ast`，`512263f`。
- 用户约定：中文回复；直接本地commit，不创建PR；本轮不推送。
- 已完成：Sol修改独立构造字段checker及其负例；主代理审查并集成显式CLI
  选项、前提绑定门控、CLI回归、协议和真实报告验收。
- API：`constructor_values.check(..., declaration_intervals=None)` 默认保持v1
  常量模式；显式闭区间表使用v2，逐步检查整个区间经过整数转换后值保持。
  字段区分constant/interval，符号区间不填单一value；报告仅列实际消费的区间
  声明前提，不把表内未用的列数区间列作grid转换前提。
- 未建立前提：源码报告忠实性、区间真实性、源guard语义、目标ABI一致性。
  CLI只检查元数据绑定，不重新验证这些语义。host有效性、实际launch、shared
  容量、线程坐标和GPU等价均未建立；不可部署。
- 未执行：新源码编译、GPU运行、MI250/native64、调优或外部共同案例。
- 工作区改动与本交接一起提交；工件仍仅在本地，不是公开复现包。
- 下一项：关联kernel形参的输入区间与列递推、行偏移的转换义务，再连接尚未
  建立的线程坐标/collective语义；同时保留G1尚未通过的研究边界。

## 实际验收

主代理 `make check`：236项通过；小位宽4→3bit的136个闭区间与逐值可表示性
枚举交叉一致，另覆盖错误ID、类型、重复域、区间部分越界和预算。

```bash
PYTHONPATH=src python3 -m wavebridge.configuration_check \
  artifacts/wb03-source-launch-guards-01/report.json \
  --abi examples/abi/int32-conditional.json --use-host-guard-assumptions \
  --output artifacts/wb03-source-launch-guards-01/configuration-interval-check-01.json
```

退出0，条件字段域checked：grid.x为闭区间[1,8]，grid.y/z均1；block字段为
256/1/1。`source_program_checked=false`、`deployable=false`。只用了行数声明
区间，未将符号参数改成某次实际行数。

```bash
PYTHONPATH=src python3 -m wavebridge.configuration_check \
  artifacts/wb03-source-launch-guards-01/report.json \
  --abi examples/abi/int32-conditional.json \
  --output artifacts/wb03-source-launch-guards-01/configuration-default-check-02.json
```

退出2，默认模式仍unknown。主代理读取两个报告断言范围/标记、输入和全部实现
哈希一致；将真实报告区间的内存副本下界改成-1后，checker返回
`integer_conversion_not_value_preserving`，原始报告未改。这是区间模型负例，
不是改写kernel后的GPU失败。`git diff --check`通过。
