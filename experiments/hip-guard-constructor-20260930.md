# 守卫后的标量值连接到构造字段

基线`6a43aa2`，分支`wb03-source-ast`。本轮重放上一轮隔离候选的完整AST，
不重新生成候选、不编译原HIP、不运行程序或GPU；fixture分别编译为Clang AST。

## 保证与复用

复用source-guard→query/minimum/quotient数值链、两个内部history检查、
scalar argument effects、constructor field forwarding及整数转换检查。
新增组合不接收手填字段值或成功报告；先保持两标量到构造入口，再检查
无写入实参、逐层转换保值及真实参数到字段映射，停止在正常构造完成。
不按x/y/z名字推断映射，不证明后续对象复制、launch或跨波宽等价。
外部整数ABI明确提供int32/unsigned-int32；API/noreturn/有效源语义等前提保留。

## 实际重放命令

```bash
mkdir -p artifacts/wb-hip-guard-constructor-20260930-02
PYTHONPATH=src python - <<'PY' > artifacts/wb-hip-guard-constructor-20260930-02/report.json
import json
from wavebridge.verification.field_snapshot import check_guarded_query_constructor
p=json.load(open('artifacts/wb-hip-query-guard-candidate-20260930-01/native.json'))['payload']
r=json.load(open('artifacts/wb-hip-source-guard-20260930-01/report.json'))
abi={'int':{'bits':32,'signed':True},'unsigned int':{'bits':32,'signed':False}}
print(json.dumps(check_guarded_query_constructor(p,'0x77692424bac0','0x77692424bda8',
  '0x77692424bfb8','0x77692424c3c0',r['selection'],r['conversion_contract_assumed'],
  r['output_contract_assumed'],abi,query_guard_id='0x77692424bc18'),indent=2))
PY
```

从旧报告只读外部协议和精确选点，不读其中check结果；所有语义检查重新执行。
输入native SHA256：`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`。
对象`0x77692424c3c0`、DeclStmt `0x77692424c550`、constructor `0x77692424c510`。

## 审阅与回归

真实fixture覆盖正常字段映射、constructor交换字段后对应数值交换、历史
改写/地址逃逸、错误标量、constructor body写入、跨函数对象、缺ABI、预算
及输入不变性。复核要求新索引还应覆盖array_filler；已补该扫描与隐藏
冲突literal负例。负例重新绑定外部协议，明确排除“仅因旧hash不匹配拒绝”。
角色计数使用独立literal count，避免字符串哨兵与声明ID碰撞。
首次01及早期日志是补强前运行，不作为最终冻结实现的验收。

## 冻结版本验收

- `make check`：1370项，176.793秒，全部通过，无跳过。
  日志`/tmp/wb-guard-constructor-check-final.log`。
- Clang23 native专项24项74.646秒，Clang17专项24项74.410秒，均通过。
  日志`/tmp/wb-guard-constructor-clang{23,17}-final.log`；插件与编译器
  使用上一轮固定toolchains，分别显式设置WB_ENUM_CAPTURE_PLUGIN与
  WB_ENUM_CAPTURE_COMPILER。
- 全测沿用上一轮六类工具链变量配置：visibility/unary/using-shadow与enum
  使用Clang23，native capture使用Clang17，未用缺工具跳过代替验收。
- `make demo`、`git diff --check`通过；Sol最终只读复核未发现阻断。
- field_snapshot.py SHA256：
  `82fc8a54d41947c6595662de55662d35c681407eedd81b18b87187a31be78602`。

最终02报告为条件`checked`，字段`0x2ca677a8`/`0x2ca67810`/`0x2ca67878`
依实际参数映射得到[32,32]/[4,4]/[1,1]；field_domains_under_source_guard为true。
post_construction_history_checked、launch_binding_checked、source_program_checked、
deployable仍为false。报告SHA256：
`72f18b4f9f0c534cab54ceb77e6cd939d5773e2f6daa7ee9c731f40e9c49597a`。
完成后再次核对native输入与外部协议来源文件hash均未改变；实现hash与上列一致。
