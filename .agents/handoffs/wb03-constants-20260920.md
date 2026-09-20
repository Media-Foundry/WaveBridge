# WB-03 常量求值交接

- 基线 `8ec223a`，分支 `wb03-source-ast`；中文、直接 commit，不创建 PR。
- 新增受限 signed-int 初始化表达式求值及单元/真实 Clang 回归。精确 ID 解析引用，保留来源，位宽须显式提供。
- 当前 HIP compiler 宏已核对 int 宽32；在 `artifacts/wb03-tu-hgtXLo/rmsnorm-tu-single.json` 上实际求得32和256。
- 修正真实 Clang 的 const int LValueToRValue 路径；INT_MIN 除/模 -1 都拒绝，非支持类型/转换不强行求值。
- 本地 `make check` 106 项通过，其中4项需真实Clang；无新GPU数值或性能运行。
- 局限：常量的语义角色尚未分类，线程getter仅人工核对到OCKL调用链，没有自动解释或跨lane关系检查。
- 下一步：限定入口可达表达式，建立getter定义到外部索引语义的可追溯前提，再分析列遍历与shuffle参数，不能仅识别名称。
