# 数组实参与声明容量

- 日期2026-09-20；分支wb03-source-ast，基线1244528；中文、直接commit，无push。
- 新模块analysis/shared_storage.py回定位同root的caller/callee定义、精确调用与
  参数位置；只接受直接数组引用的单次ArrayToPointerDecay和括号。
- 数组须为caller顶层调用前的声明，指针/算术/任意cast/错误声明均unknown。
  保留实参AST、类型、属性、声明范围，静态float[N]只记录元素数，不猜字节数。
- CUDASharedAttr区分shared证据与普通CPU数组。无界shared要求launch bytes，
  普通无界extern要求外部分配；不把调用成功、宽度或静态声明当成容量验证。
- chain增加独立shared_storage字段，unknown不升级为存储成功；旧结构链结论不变。
  source入口绑定新增实现哈希。
- `make check`295项通过；测试包括正常绑定、参数换序、extent2、无界extern、
  非法cast、缺失声明ID，以及AST注入extern/shared属性时不把extent视为静态分配。
  最后一项仅分类回归，不代表该语法经过HIP验收；Sol审查意见已纳入。
- 真实HIP重采集命令沿用上一交接，最终输出为 `artifacts/wb03-shared-binding-02`。
  01为审查硬化前的历史工件，保留不覆盖。
  chain recovered，shared_storage recovered，argument_index=1，shared_dynamic，
  extent_elements=null，capacity_status=launch_bytes_required。
- report.json SHA256：`7147d250e21c502aa51c3b1dc5bbeb10a4b2ee7b278d5e1d988e91591707a4d9`
- ast.json SHA256：`3a21881e8de662797909661ba9319dd080a449a7bf2a55c32670501e20d53045`
- 未运行GPU、未更改数值协议。别名、属性目标语义、运行时分配容量与launch字节数
  尚未证明；后续应绑定launch第三配置实参及显式元素ABI，独立检查存储需求。
