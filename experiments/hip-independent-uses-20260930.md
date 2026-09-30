# 不依赖初始化数值域的真实对象引用检查

基线`41034db`，分支`wb03-source-ast`。旧对象结构入口因selection_domain_missing
停在数值初始化，新入口只分离结构义务，不删除数值或历史义务。

## 命令

```bash
mkdir -p artifacts/wb-hip-independent-uses-20260930-01
PYTHONPATH=src python - <<'PY' > artifacts/wb-hip-independent-uses-20260930-01/report.json
import json
from wavebridge.verification.object_use_closure import inspect_uses
p=json.load(open('artifacts/wb-hip-query-guard-candidate-20260930-01/native.json'))['payload']
abi={'int':{'bits':32,'signed':True},'unsigned int':{'bits':32,'signed':False}}
print(json.dumps(inspect_uses(p,'0x77692424c3c0',abi,
    instantiated_function_id='0x2d7f1410',max_ast_nodes=1000000),indent=2))
PY
```

输入native SHA256：
`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`。
实现object_use_closure.py SHA256：
`436deb888082358b9ab0e193e47b32453dd5694f371735702ed91a961b7b754f`。
不读取上一轮数值报告，也不手填32/4/1。

## 接口与验证范围

inspect_uses使用独立schema，与原inspect_structure共用内部结构扫描；旧
入口行为不变。新入口声明初始化值/效果/cleanup/完成未建立，扫描inner与
array_filler。字段值、执行路径、源存活、历史保持、API和部署继续未建立。

真实Clang fixture用函数参数提供未知初值，在switch两分支复制对象：旧接口
unknown而新引用结构可检查。测试patch初始化入口以确保新入口不调用它，
并覆盖写入、引用别名、static/TLS、预算、隐藏array_filler身份或引用。
首轮fixture外部未定义函数导致三项既有CPU执行测试链接失败，已改为参数输入；
初轮日志保留`/tmp/wb-independent-uses-tests.log`，不作为验收通过记录。
测试会执行既有小型CPU语义程序，本轮没有重新编译或运行HIP/GPU。

## 已完成验收

固定Clang17/native插件专项48项30.747秒通过；全测1376项179.203秒通过
无跳过。日志`/tmp/wb-independent-uses-tests-final.log`及
`/tmp/wb-independent-uses-check.log`。全测工具链变量沿用此前配置：native
capture为Clang17，visibility/unary/using-shadow/enum为Clang23。
make demo与diff检查通过；Sol只读复核无阻断。

额外Clang23对象专项48项有29个失败，不列为通过；本轮新两项均通过。
以git show 41034db版本object_use_closure模块替换当前模块，使用相同fixture、
Clang23/plugin并排除两项新测试后，46项中出现完全相同的29个失败项。
旧实现不含inspect_uses，基线测试注入的占位入口一旦被调用即抛错，未被调用。
差异集合均为空；这证明本轮没有增加该专项的失败项，不证明完整Clang23
捕获路径可用。失败主要涉及capture_field_not_exact_source_reference_member
及类型支持，不通过切换统计口径隐藏。
日志`/tmp/wb-independent-uses-clang23.log`、
`/tmp/wb-independent-uses-clang23-baseline.log`保留。

## 真实重放结果

报告SHA256：`b35b6907a451455d2fae185fb5e9f55b75104ea0d3e104c2b11d9094b53af8b5`。
同一函数内22个显式引用、22个direct copies，零capture/lambda；父结构checked。
22次copy的parameter_target与object_boundary均checked；source_reference_use_effects、
copy_cleanup_observations、local_record_cleanup_scopes均checked，但scope各自保留。
source_order仍unknown（source_order_do_outside_source_scope），继而
preceding_expression_cleanups为unknown（preceding_cleanup_source_order_not_checked）。
conditional_initialization=null，初始化值/effects/cleanup/completion及历史仍未建立，
deployable=false。下一步定位真实do/switch结构限制，而不是用父级checked放行。
