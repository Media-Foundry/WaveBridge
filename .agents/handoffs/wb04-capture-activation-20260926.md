# 同次包围函数求值的源码绑定

- 2026-09-26；分支wb03-source-ast，基线2823992，其CI36231867058已success。
- 新capture-source-assumptions/v3删除origin和same-activation布尔；v1/v2
  精确键集与保证不改。alive、source-valid仍严格必须为true。
- 在既有checker内核对唯一ordinary FunctionDecl、直接CompoundStmt body、
  source为DeclStmt/CompoundStmt自动局部，source/copy路径属于同一精确body。
  同时核对完整capture chain序列和逐层fresh原始receiver/call/body路径。
- function-try-block和coroutine不支持；普通函数体内部try未被这项门控一概
  拒绝。结论是copy求值时同一包围函数求值，不等于source活着、执行一次或值保持。
- 语义依据/推导边界写入compiler/verification/README.md，引用C++ draft
  basic.stc.auto和expr.prim.lambda.capture。标准条款不是本checker正确性证明。
- GPT-5.6 Sol只读复查未发现阻断问题。

## 已执行验收

匹配Clang17原生插件启用。16项capture定向通过；最终make check为669项，
Clang专项193项，demo退出0。日志artifacts/wb-capture-activation-AunFA6/
tests.log、clang.log、demo.log。命令沿用上一交接的WB_NATIVE_CAPTURE_PLUGIN
及WB_NATIVE_CAPTURE_COMPILER设置；专项为PYTHONPATH=src python3 -m unittest
discover -s tests -p '*clang*.py'。

真实递归raw-immediate源码正例+CPU深度0～4，确认递归返回后仍复制当前source。
真实具名/传出/返回、外层by-copy、source-inside-lambda、static/TLS等负例。
coroutine形状是合成AST边界测试，不计为真实C++20 coroutine执行。顶层
object_use_closure跨层正例分别用v2/v3执行。没有GPU执行。

## 完整TU重放结果

命令WAVEBRIDGE_JSON_HASH_MODE=one-shot PYTHONPATH=src python3 artifacts/wb-capture-activation-AunFA6/check.py。
exec session2874已退出0，PID231726已结束。run.log为日志，report.json为终态工件。
固定完整原生TU SHA256 f80432e744686fdc1390308073a3cd7e1b1d1ba5afd065198dcc292ab21ee9ee。
从原协议仅迁移版本和删除origin/activation布尔，其余外部条件不改；不读取旧
成功子报告。fresh检查全部链，前后77个实现文件哈希一致，并通过sha256sum
--check复核当前源码匹配。源码冻结已解除；没有重启任务。
耗时662.0844317199953秒；主引用闭合、source_order、use-effects均checked。
3个capture-source-check/v3及closure_origin全部checked；activation精确绑定
function0x3736fa78、body0x373938c8、source DeclStmt0x37370ea0。
每份最终premises仅保留source_initialized_alive_assumed/source_program_valid_assumed。
报告SHA256：399c710c1478aceb8476f6fe0aad917d77c29f03afd1d8bbcb99b1d520566ff5。
这是fresh v3结果，不是把旧v2结果改标签；未执行GPU。
f665cd2的远端CI36232126716已success。

任务终态已核验；下一步处理alive/初始化完成与生命周期义务，不直接
删除剩余假设或把历史值保持宣称完成。中文、直接commit/push，无PR。
