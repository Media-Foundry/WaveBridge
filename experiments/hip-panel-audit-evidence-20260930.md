# 冻结 HIP 面板的离线证据审计

基线 `cb5d739`，分支 `wb03-source-ast`。本轮没有启动GPU，没有生成新预测。

## 为什么增加这项验收

静态host入口组合以[65,128]为外部域，不能从历史GPU结果自动继承输入语义。
本轮先独立审计可供后续协议绑定的历史事实，不向checker注入width=32或调用域。
`softmax_panel_audit`重新核对固定报告、完整笛卡尔积、命令参数与原始stdout，
用当前已哈希的独立reference重新评分，不信任报告中的numerical passed字段。
还重读当前适配源码、补丁与二进制核对历史哈希；不会执行二进制。

## 命令

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_panel_audit \
  --report artifacts/wb-softmax-hip-pilot-20260927-10/report.json \
  --report-sha256 f53b5800c54e8ef5ec459b7734e3c4edf0a6064e8e519357881926e28b78cab2 \
  --output artifacts/wb-hip-panel-audit-20260930-02/report.json
```

最终报告SHA256：`29e6e3eca912b43e835bd6129f475f4eac571496ef4804d04048cb4c6de0cfc8`。
首轮01报告`048250c73cb56e25b7e6901e824ea976e28e303434b6a59417585ff57f969622`
保留；最终版增加严格JSON解析及逐案例fresh误差/stdout哈希。两版都绑定协议
验证器、reference与审计脚本本身的内容哈希。重复字段和非标准NaN/Infinity
不能被宽松解析后当成一致证据。
状态recorded_panel_rechecked，18项完整，列数仅{65,128}、行数{1,3,17}、
三种冻结pattern；各记录API/device width=32、block=[32,4,1]、launch次数1。
实际二进制SHA256仍为
`e701e27e45191a6db5d0ea8aa4412f3300db1f99b00c6da5d29d541276750978`。

## 尚未建立的连接

main源码用std::stoi读取columns，按端点面板过滤，再以同一columns传入dispatch
的第三/第四个实参；这是本轮源码阅读观察，不是新静态checker结论。其完整
前缀包含运行时API、分配和复制等调用，现有parameter_entry不覆盖该主函数。
不能因main中有if或columns是const便省略别名、转换、调用/机器码对应义务。

审计没有重查当前加载库、编译元数据或设备状态；库路径/哈希仅保留为历史记录。
报告明确保留host_parameter_domain_proved/API_semantics_proved/source_program_checked/
deployable=false。连续域[65,128]没有得到64种GPU尺寸测试支持。
这项审计也不宣称验证全部运行时环境或所有原始构建输入。

## 回归

合成记录测试覆盖缺项、重复、错误命令、stdout不一致、伪造数值passed、
bool冒充整数、宽度不符、混合库身份、源工件修改和固定报告哈希不符。
fixture不是GPU证据；历史真实报告的重放另行执行，二者明确区分。

最终定向4项通过；完整make check为1302项、97.906秒、无跳过，日志
`/tmp/wb-panel-audit-final-check.log`。使用既有SDK23 visibility/unary/using
及AOCC17 native插件组合，未简化为基础无插件测试。demo/diff通过，Sol最终
只读复核无阻断。审计重算的历史最大绝对误差1.6796065205326727e-08、最大
行和误差7.594798701049399e-08，仅来自已有原始输出，不是新增GPU实验。
