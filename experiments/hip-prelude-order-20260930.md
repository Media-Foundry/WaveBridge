# 真实对象之前的 do-while(false) 结构顺序

基线`ad40282`，分支`wb03-source-ast`。上一轮source_order因
source_order_do_outside_source_scope为unknown，本轮不是跳过该义务。

## 原AST定位

完整函数`0x2d7f1410`中只有一个DoStmt `0x77692424b800`，是外层Compound
`0x7769241d9c80`的直接子节点；对象位于后续IfStmt `0x7769241d9c50`内，
源scope为`0x7769241d9be0`。switch `0x77692424c5a0`在源scope内。
原do条件通过已有精确false检查，不是动态循环。

新增规则要求do/source路径在共同Compound分叉且前者直接兄弟位置更早；
原do唯一ID/body/精确false条件、全函数禁用控制流、所有break/case归属门槛
全部保留。前置body可能执行、返回或改变全局；本报告不判它无副作用，也不
证明源码必达或初始化完成。不能将false条件误读为body被跳过。

## 实际重放命令

```bash
mkdir -p artifacts/wb-hip-prelude-order-20260930-01
PYTHONPATH=src python - <<'PY' > artifacts/wb-hip-prelude-order-20260930-01/report.json
import json
from wavebridge.verification.object_use_closure import inspect_uses
p=json.load(open('artifacts/wb-hip-query-guard-candidate-20260930-01/native.json'))['payload']
abi={'int':{'bits':32,'signed':True},'unsigned int':{'bits':32,'signed':False}}
print(json.dumps(inspect_uses(p,'0x77692424c3c0',abi,
    instantiated_function_id='0x2d7f1410',max_ast_nodes=1000000),indent=2))
PY
```

仍是同一冻结native输入，SHA256
`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`。
实现object_use_closure.py SHA256
`6c089fdd135970d6c88bf062839c17e8d026ff4d40e20ad48ca6d971b1802d86`。
不读取旧成功报告、不手填数值域，不重新编译或执行HIP/GPU。

## 回归

真实fixture覆盖同块前置do、外层前置do加内层对象/switch；动态条件、后置
旁支do、包围源声明的do保持unknown，隐藏goto/continue/case仍拒绝。
Clang17对象专项50项32.976秒通过，日志`/tmp/wb-prelude-do-tests.log`；
Clang23只运行本轮新增两项并通过，日志`/tmp/wb-prelude-do-clang23.log`。
此前完整Clang23捕获专项兼容性缺口未在本轮修复，不能宣称全专项通过。
Sol只读复核无阻断；专项含既有小型CPU程序执行，不是GPU实验。

固定工具链全测1378项182.912秒通过，无跳过；日志`/tmp/wb-prelude-do-check.log`。
沿用native capture Clang17及visibility/unary/using-shadow/enum Clang23的配置。
`make demo`与`git diff --check`通过。

## 最终真实结果

报告SHA256：`66fc21545f269a2261577699fdaa65f0bf4165767df322b8ee7dd186969e4ac6`。
22引用/22直接复制仍完整；source_order、source_reference_use_effects、
copy_cleanup_observations、local_record_cleanup_scopes及preceding_expression_cleanups
均checked。前置do与source所在分支在共同外层Compound的位置分别为0和1。
前序cleanup wrapper选择/排除清单均为空，这只表示该受限观察没有选中wrapper，
不是全部动态析构或调用效果不存在。conditional_initialization仍null，
初始化值/效果/cleanup/完成与对象历史未建立，deployable=false。
重放结束后实现hash与前述一致，未使用旧报告或旧子结论代替fresh检查。
