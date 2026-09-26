# 条件有序加载元素下标

- 日期/分支/基线：2026-09-26，wb03-source-ast，ff9806e；初始工作树干净。
- 用户约定：中文、直接 commit/push 工作分支，不 PR、不合并 master。
- 实现：双侧 v5 的私有 fresh-child 组合连接 local/column 精确递推、唯一
  range 匹配、coverage、block/step、角色、row*count 偏移、坐标与 effect。
  比较相对各自 input 参数基址的有序逻辑元素偏移 r*n+t+k*B、k>=0、t+k*B<n。
- 保证范围：共同 r/n/t 是条件关系的符号，不是实际执行已配对的事实；
  runtime_pairing_verified false，input contents/leaf values 未建立，source/
  deploy false。不是指针有效性、地址相等、FP 或机器码证明。外部前提不变。
- 验证：匹配 native 插件下 make check：819 tests，63.002 秒，OK；make demo
  和 diff 检查通过。4 项 fixture 方法、1 项真实 Clang source.run 负例方法、
  1 项 mock 顶层传播。枚举独立 while 与全部规范式系数作小域交叉验证，
  不把枚举当一般性证明或部署验收。真实 shifted load/row 均 unknown。
- Sol 子代理：只读核对算法边界、实现新增测试、再只读复核；未发现阻塞问题。
- 工件：artifacts/wb-load-indices-vLsfh0/，包含 tests.log、tests-final.log、
  demo.log、run.py 及显式未验证 effect 条件协议；真实重放结果由主代理追加。
- 没有执行：GPU、HIP 新编译、性能测量；没有修改冻结的数值验收协议。
- 下一步：建立实际/抽象输入对象及每个对应位置的值关系，并规定相同局部
  FP 执行语义，再研究局部 accumulator 对应。不要用参数位置、相同下标或
  相同数值域直接声称加载值相等，也不要跳过 alias/并发写和运行参与前提。
- 提交/推送：全部验收后统一执行，不提交本地大工件。
- 最终真实 v5 重放：356.649 秒，退出 0；load_index_relation checked，两侧
  r*n+t+256*k，r=0..7、n=1..1023、t=0..255；父 evidence，实际配对未验证、
  输入内容/叶值未建立；实现哈希稳定。report.json SHA256：
  adfc88aceb63b338859dd0cd9108a452bc5a65993dd98a101e7ff183c5a9c785。
