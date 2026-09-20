# 交接：受限 OCKL shuffle 编译诊断

- 日期/分支/基线：2026-09-20，wb03-source-ast，7ed328d；中文，直接commit，无PR/push。
- 输入：artifacts/polygeist-ockl-shuffle-YshEjS/adapter.cu，hash
  `87aab91bf2bdfea34b3eb762dc43bc37a389954af2063a82d9d92a07767bb1bb`。
  基于static shared+OCML诊断副本，把shuffle替换为人工diagnostic_xor32；
  用已有__ockl_readuplane_i32和delta=(lane^offset)-lane，lane显式为signed int。
  两次__builtin_memcpy搬运4字节，static_assert float/int大小。原案例/编译器不改。
- 条件：1D block256，物理lane与线程线性索引连续对应，全lane在五轮offset
  16/8/4/2/1处活跃且收敛，logical32，非部分mask/width64/发散的通用实现。
  调用及声明加convergent，但尚未证明该属性在整个编译链中保留。
- 固定库readuplane.cl硬编码WAVESIZE64，按lane_id+delta取值；lane.cl依赖
  __oclc_wavefrontsize64。数学上wave64两半波封闭、wave32目标始终0..31。
  实际用Python枚举wave32/64、tid0..255与五offset，共2560项路由通过。
  这只验证条件整数公式，不建立物理lane映射、库控制常量一致性或FP保证。
- 编译参数与环境沿用OCML交接：显式SDK LD_LIBRARY_PATH、PYTHONPATH=src，
  固定cgeist/O0/function=*/gfx1100/sm_70/backend-view，禁止cuda-lower。
- LLVM尝试：artifacts/polygeist-frontend-0fnyd40g/report.json，hash
  `2725101f870879e609b59b071452cd89efec009a1c372c660bd6c848c9737df2`。
  returncode=-6，ir=null；在diagnostic_xor32的AMDGPU DAG指令选择中触发
  SelectionDAG.cpp:5435 Cannot BITCAST between types of different sizes断言。
  报告保存原始argv/栈/stderr，未得到HSACO，不说它只是链接失败。
- GPU MLIR尝试：artifacts/polygeist-frontend-38mlz6yz/report.json，退出0，hash
  `07f1677a6af47103b854216757bf44eb39d50a3926f9176c98d865bc04659523`；
  output.mlir hash `70feda2c41b74da5444a967e4b80b7c5171cf4528692dd52533c20828dbec52f`。
  helper含局部memref.alloca、memref2pointer到generic i8指针、位搬运及OCKL调用。
  地址空间/位搬运是待查方向，不能凭栈断言已证明根因或路由错误。
- 子代理独立审计确认条件公式；其unsigned差风险在本副本由显式signed lane避免。
  仍需核实固定serializer的wave64库常量与gfx1100 wave32生成的关系。
- 未执行GPU加载/数值/性能；不声称自动关系恢复、新lowering算法或适配成功。
- 下一步：保存序列化前设备LLVM诊断，定位不等宽bitcast并与局部位搬运输入对照；
  不用不受定义的union/指针别名替换来换取表面通过，不扩大为通用编译器修复。
