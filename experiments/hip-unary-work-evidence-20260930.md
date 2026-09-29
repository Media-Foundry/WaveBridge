# HIP guarded work 中的一元条件效果

2026-09-30，基线`b163b0e`。

## 范围与选点

真实HIP同一softmax实例中，4处exp属于没有break的计算循环，不适用当前
guarded-work入口；log位于带退出守卫的外层输出循环`0x745c579c4018`。
驱动选择含已登记math call及break的语法ForStmt，不是穷尽循环清单，
也不将嵌套节点数记作独立kernel数。

本轮不开启静态分支裁剪，保守检查两臂；开启既有nested-loop检查。从旧
固定哈希工件只读取未验证效果协议，不消费旧checked或成功子报告。
每个实际消费调用、循环头/守卫/工作区都在原native AST上fresh检查。
int32为外部ABI前提，不是本轮设备测量。

## 命令

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_unary_work \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --math-protocols artifacts/wb-hip-native-effect-20260930-01/report.json \
  --zero-protocols artifacts/wb-hip-native-20260927-01/conditional-work.json \
  --output artifacts/wb-hip-unary-work-20260930-01/report.json
```

输入SHA依次为：

- `46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`
- `a8af8a027126343d9221d593efdd2a1e709b1ba1588d89ee129fcf21fa9f617b`
- `7952d53d103ccbf4c130fc4c775a67b726a039b4c652eddc4b270dc42939de87`

不重编译生产TU、不运行GPU、不认证设备库效果。

## 实现与验证边界

work入口显式传播一元/using选项，默认False。策略绑定输入hash，实际消费
调用的全部假设进入父报告。其它写入、未知调用、unused协议仍使整体unknown。
真实Clang回归包含正常guarded循环、limit写入、实参写入、仅部分调用有协议
以及nested调用假设传播；输入工件校验fixture不当作源码覆盖证据。

GPT-5.6 Sol只读复核未发现P1；已补双call和nested传播的建议回归。
报告继续保留external_call_effects_verified、full_iteration_domain_established、
source_program_checked、deployable为false，不把条件存储保持扩展成FP保证。

## 实际结果

重放退出0，`observed`，输入/src实现/driver hash运行前后一致，结束后再与
当前输入和文件核对一致。报告SHA256：
`895bf85d521d3401cfa7f025fb672d256ec9d2ec218dc1269c9621303efa59e7`。

| 模式 | 同一外层输出循环结果 | 原因/范围 |
| --- | --- | --- |
| 默认一元禁用 | unknown | call_effect_not_checked |
| 显式一元/using启用 | checked | guarded_work_preserves_dependency_storage，conditional |

两条实际消费call是`0x745c579c2e50`（log一元wrapper）与`0x745c579c3aa8`
（零参nan wrapper）；均fresh条件checked，协议无未使用项。嵌套循环
`0x745c579c3fa0`的保护义务也checked。全部子调用前提已纳入父报告并独立
复核包含关系。受保护声明为`0x745c579ba728`、`0x745c579bae48`和
`0x745c579c25f8`；这不是输出数值、整个kernel或GPU部署保证。

没有静态剪去log所在分支；结论仍以显式库效果/正常返回、源有效性、存储
不别名、对象存活和实参有效等前提为条件。先前三项输入中的成功结论未被
消费；它们只提供固定的协议字典。导入的实验辅助脚本未单独作运行前后hash
记录，不把driver自身hash描述为完整Python环境/依赖闭包。

## 测试验收

最终1263项CPU测试通过（106.134秒，无跳过），make demo/diff通过。
最初1260项106.049秒通过记录亦保留；随后补了双call、nested传播和两项
驱动输入边界回归。最终native+driver定向25项在AOCC17匹配插件下通过
（2.559秒）；SDK23 native23项通过（2.760秒）。全量的新unary/using专项
使用SDK23，旧native专项使用AOCC17，不称全量SDK23或远端CI通过。
日志`/tmp/wb-unary-work-final-check.log`、`/tmp/wb-unary-work-demo.log`、
`/tmp/wb-unary-work-aocc-final.log`、`/tmp/wb-unary-work-targeted-final.log`。
