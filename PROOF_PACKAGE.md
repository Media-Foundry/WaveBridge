# Proof Package

## Claim

对两个已经通过贡献计数检查的两阶段 block 路由，设共同叶值为
$z_0,\ldots,z_{B-1}\in[0,M]$，$S=\sum_i z_i$。在下述局部误差模型及路由
前提下，`block_roundoff.compare` 返回 checked 时，其每个输出线程满足
$$
|\widehat S_s-\widehat S_t|
\le (r_s+r_t)S+A_s+A_t
\le (r_s+r_t)BM+A_s+A_t.
$$
这里 $r_j=(1+u)^{d_j}-1$，$d_j$ 是该侧输出的最大加法路径深度，$A_j$ 是
下文递推的绝对误差余量在所有输出中的最大值。结论只关于显式路由模型，
不是实际 HIP、源程序或完整 RMSNorm 的数值验收。

## Status

PROVABLE AS STATED（仅上述带明确假设的模型命题）。
“真实 RMSNorm 满足冻结容限”仍是 NOT CURRENTLY JUSTIFIED；未将其替换为本命题。

## Assumptions

- 两侧具有相同 $B$ 个共同、精确、非负叶值，并且 $0\le z_i\le M$。
- 每个输出的展开表达式包含每个叶值恰好一次；填充叶值精确为零。这由已有
  贡献计数检查在其显式路由模型内核对；对源码的对应另待建立。
- 每个加法的实际模型结果 $f(a,b)$ 非负，且在有限范围内满足
  $$|f(a,b)-(a+b)|\le u(a+b)+\eta.$$
  固定 $u=2^{-24}$、$\eta=2^{-150}$，$F=(2^{24}-1)2^{104}$。这是显式外部
  误差律，不在此宣称已证明真实 GPU、FTZ、重排或编译器均满足它。
- $a,b\ge0$ 且 $a+b\le F$ 时，上述误差律适用且模型操作有定义。实现用更
  强的输出上界不超过 $F$ 的条件确保每个操作进入这一范围。
- 全参与、快照 XOR-add、共享写入可见性、写入者与加载位置遵循显式模型。

## Notation

每个展开节点 $v$ 的精确实数子树和为 $T_v$，计算值为 $\widehat T_v$。
其状态为深度 $d_v$、余量 $A_v$ 和计算值上界 $U_v$。输入叶的状态为
$(0,0,M)$，零叶为 $(0,0,0)$。加法节点的子节点记为 $a,b$，其状态递推为
$$
d_v=1+\max(d_a,d_b),\quad
A_v=(1+u)(A_a+A_b)+\eta,\quad
U_v=(1+u)(U_a+U_b)+\eta.
$$
实现逐节点要求 $U_v\le F$；不满足只返回 unknown，不能据此断言程序溢出。

## Proof Strategy

按展开加法树进行归纳。DAG 共享值按每次使用展开，不能因存储共享而漏计其
误差出现次数；实现的加法递推正是按两个操作数分别累加余量。先建立值域与
上下包络，再取两侧相对共同精确和的误差之和。

## Dependency Map

1. 有限非负值域依赖非负叶值、局部误差律与逐节点的 $U_v\le F$ 检查。
2. 子树包络依赖值域、深度递推和绝对余量递推。
3. 输出精确和为 $S$ 依赖每个真实叶贡献恰好一次。
4. 两侧差值界依赖相同叶值及三角不等式，不依赖两侧舍入误差独立。

## Proof

### Step 1：有限值域

叶值非负且不超过其 $U_v$。假设两个子节点满足
$0\le\widehat T_a\le U_a$、$0\le\widehat T_b\le U_b$。
检查条件 $U_v=(1+u)(U_a+U_b)+\eta\le F$ 蕴含
$\widehat T_a+\widehat T_b\le U_a+U_b\le F$，因此局部误差律可用。
由该误差律和非负结果假设得到 $0\le\widehat T_v\le U_v$。
这建立每个节点的有限范围，不以待证明的数值包络反向假定无溢出。

### Step 2：子树包络

证明对每个节点有
$$
(1-u)^{d_v}T_v-A_v\le\widehat T_v
\le(1+u)^{d_v}T_v+A_v.
$$
叶节点深度与余量均为零，故成立。对加法节点，局部误差律给出
$$
(1-u)(\widehat T_a+\widehat T_b)-\eta
\le\widehat T_v
\le(1+u)(\widehat T_a+\widehat T_b)+\eta.
$$
对上界代入两个子节点的归纳上界。由于 $T_a,T_b\ge0$ 且
$d_a,d_b\le d_v-1$，系数各不超过 $(1+u)^{d_v}$，常数项恰为 $A_v$。
对下界代入两个子节点的归纳下界。因 $0<1-u<1$，两个正的精确和系数
各不小于 $(1-u)^{d_v}$；被减余量为
$(1-u)(A_a+A_b)+\eta\le A_v$。以较大的 $A_v$ 替代，得到所需下界。
即使下界为负也仍有效；没有将它解释为负的实际计算值。

### Step 3：相对共同精确和的对称误差界

对整数 $d\ge0$，二项式展开得到
$(1+u)^d+(1-u)^d\ge2$，因为奇次项抵消，其余非恒定项非负。
因此 $1-(1-u)^d\le(1+u)^d-1$。
输出每个叶贡献恰好一次，故 $T_v=S$。从 Step 2 的两侧包络可得
$$|\widehat T_v-S|\le[(1+u)^{d_v}-1]S+A_v.$$
以该侧最大深度和最大余量代替仍有效，因为 $S\ge0$。

### Step 4：双侧比较和边界情况

对两侧应用 Step 3 并用三角不等式得到 Claim 第一条不等式。
$S\le BM$ 与 $r_s+r_t\ge0$ 给出第二条。$M=0$ 或 $S=0$ 时推导仍有效，
只是保守保留了正的绝对余量，不声称该界紧。深度零的子树在 Step 2 基础项
已经覆盖。输入不符合域、贡献重复/缺失或无法建立有限界时，不产生本结论。∎

## Corrections or Missing Assumptions

不能从 $x\in[-2,2]$ 直接把已经舍入的局部 accumulator 上界写成 $16$；
局部累计的舍入仍需单独分析。传入的 $M$ 只是外部条件，尚未从真实源码建立。

## Open Risks

- 误差律的真实工具链/设备适用性、输入叶对应、源到模型对应仍未验证。
- 除法、epsilon 表示、rsqrt 误差及输出乘法不在本证明内。
- 证明对应数学算法，Python 实现本身没有机器验证；回归不是一般证明。
- 这是一条常规前向误差界，不单独构成研究新颖性主张。

## Extension Claim：局部平方累计与归约组合

状态：PROVABLE AS STATED，仍为条件模型命题。原始路由命题不变，扩展不再
要求两侧**计算后的**局部叶相同，而要求共同的原始行输入。

### Assumptions and Notation

行长 $N\ge1$、$|x_j|\le X$、$q_j=x_j^2\ge0$。线程 $t$ 处理且仅处理
$j=t+kB<N$，有 $m_t=\max(0,\lfloor(N-1-t)/B\rfloor+1)$ 项，初值为零。
这些索引集合不交并覆盖整行，定义 $T_t=\sum_{j\text{ assigned to }t}q_j$，
$Q=\sum_tT_t$。$\widehat L_t$ 表示局部计算结果。保留原有非负计算结果、
有限范围和归约前提；局部模式由外部显式指定：

- FMA 模式：$p'=f(p,x)$，$|f(p,x)-(p+x^2)|\le u(p+x^2)+\eta$。
- 分离模式：$\widehat q=g(x)$，$|g(x)-x^2|\le ux^2+\eta$，再应用原加法误差律。

模式对应编译器的实际选择尚未由本检查器建立；两侧可以使用不同模式。输入
按已经提供的精确值解释，不增加从其他dtype加载/转换的隐含舍入假设。

### Dependency Map and Proof Strategy

1. 逐次局部递推给出每线程误差与非负有限值域。
2. 不交列覆盖把局部精确和汇总为 $Q$。
3. 原路由单侧误差命题作用于该侧实际局部叶，再用三角不等式连接到 $Q$。

### Proof Step 1：每线程局部界

对 $m$ 项的FMA累计，设 $a_m=(1+u)^m-1$、$b_0=0$、
$b_{k+1}=(1+u)b_k+\eta$。反复应用FMA局部律并使用每个 $q_j\ge0$，
每个精确项的上系数不超过 $(1+u)^m$，下系数不小于 $(1-u)^m$，
上下余量均由 $b_m$ 覆盖；采用前述二项式不等式得到
$|\widehat L_t-T_t|\le a_m T_t+b_m$。

分离模式的每个精确项多经过一次乘法舍入。$m>0$ 时取
$a_m=(1+u)^{m+1}-1$，$b_{k+1}=(1+u)(b_k+\eta)+\eta$；$m=0$ 时取
$a_0=b_0=0$。每个项经过一次乘法和至多 $m$ 次加法，故上系数不超过
$(1+u)^{m+1}$、下系数不小于 $(1-u)^{m+1}$。每步新增乘法余量在随后的
加法中乘以 $1+u$，再增加加法余量，所以该递推覆盖所有绝对误差；下余量
用 $1-u$ 传播更小。再次应用二项式不等式得到同形式局部界。

计算值域独立递推。FMA模式取 $V_0=0$、
$V_{k+1}=(1+u)(V_k+X^2)+\eta$；分离模式先取
$P=(1+u)X^2+\eta$，再取 $V_{k+1}=(1+u)(V_k+P)+\eta$。
检查乘法上界和每次 $V_k\le F$；通过时确切操作数的非负精确结果不超过
这个上界对应的有限范围，才应用局部律。这沿用原证明 Step 1 的顺序，
没有以最终误差结论反向假定无溢出。无局部项的线程保持精确零。

### Proof Step 2：汇总局部误差

记 $a=\max_t a_{m_t}$、$b=\sum_t b_{m_t}$、$L=\sum_t\widehat L_t$。
列集合不交覆盖和 $T_t\ge0$ 给出
$$|L-Q|\le\sum_t(a_{m_t}T_t+b_{m_t})\le aQ+b,$$
因此 $0\le L\le(1+a)Q+b$。局部计算值上界给出路由叶界
$M=\max_t V_{m_t}$，无需假设它恰等于未舍入的数学平方和上界。

### Proof Step 3：单侧与双侧组合

对这一侧自身的实际局部叶应用原路由命题的单侧形式，有
$|\widehat R-L|\le rL+A$。这里没有假设另一侧的局部叶相同。于是
$$
|\widehat R-Q|\le [a+r(1+a)]Q+(1+r)b+A.
$$
把右侧系数及余量记为 $c,e$。两侧分别得到 $(c_s,e_s)$、$(c_t,e_t)$，
相对同一个 $Q$ 应用三角不等式：
$$|\widehat R_s-\widehat R_t|\le(c_s+c_t)Q+e_s+e_t.$$
再以 $Q\le NX^2$ 得到输入域上的绝对上界。$X=0$、部分 $m_t=0$ 和
两侧模式不同时均被上述递推覆盖；过大的循环预算只返回unknown，不扩大结论。∎

### Open Risks for Extension

此扩展仅在模型内从 $N,B,X$ 推出局部叶界及误差；真实源码对应、输入配对、
FMA/分离模式、局部和归约误差律仍是外部前提。实际除法、epsilon、rsqrt与
最终乘法继续未覆盖，不能宣称完整RMSNorm冻结容限已通过。

## Output Extension Claim：相对理想实数输出

状态：PROVABLE AS STATED，仅以下带明确外部误差律的模型命题。真实冻结
reference 的实现误差和真实设备条件尚未建立，不宣称实际容限验收通过。

### Claim, Assumptions and Notation

承接平方和扩展，每侧总和 $R\ge0$ 满足 $|R-Q|\le aQ+b$。
令 $q=Q/N$、理想epsilon为 $e>0$、实际存储epsilon为 $\widehat e>0$，
$D=q+e$、理想输出 $y_*=x/\sqrt D$。后缀严格为
$d=\operatorname{fl}(R/N)$、$E=\operatorname{fl}(d+\widehat e)$、
$g=\operatorname{rsqrt}(E)$、$\widehat y=\operatorname{fl}(xg)$。
假设整数到除数转换精确；除法和加法返回非负值并满足绝对局部误差律
$|\operatorname{fl}(z)-z|\le u|z|+\eta$；有符号最终乘法满足同一误差律。
rsqrt 的实际值在报告的正输入区间内满足外部指定的
$|g-E^{-1/2}|\le\rho E^{-1/2}$，$0\le\rho<1$。此处不猜测SDK提供了什么 $\rho$。

定义
$$
A=(1+u)^2(1+a)-1,\quad
C=(1+u)^2b/N+(2+u)\eta+u\widehat e+|\widehat e-e|,
$$
$$\delta=\max(A,C/e),\quad h=\frac{\delta}{2(1-\delta)},\quad
c=(1+u)(1+h)(1+\rho)-1.$$
若检查器建立全部有限范围且 $\delta<1$，每侧有
$$|\widehat y-y_*|\le c|y_*|+\eta.$$
两侧相对相同 $y_*$ 的误差相加，得到输出差值界。

### Dependency Map and Strategy

1. 平方和误差和两次后缀舍入给出 $E$ 相对 $D$ 的误差。
2. $e>0$ 与 $\delta<1$ 保证正的rsqrt输入，再用平方根恒等式取有理扰动界。
3. 外部rsqrt相对误差与最终乘法误差相乘组合，不假定两个误差方向独立。

### Proof Step 1：归一化分母

三角不等式与 $R/N\le(1+a)q+b/N$ 给出
$$
|d-q|\le(1+u)|R-Q|/N+uq+\eta.
$$
进一步 $d\le q+|d-q|$，代入加法误差可得
$$
|E-D|\le(1+u)|d-q|+u(q+\widehat e)+\eta+|\widehat e-e|
\le Aq+C.
$$
因为 $q\ge0,e>0$，$(Aq+C)/(q+e)$ 是 $A$ 与 $C/e$ 的非负加权平均，
所以 $|E-D|\le\delta D$。于是
$E\ge(1-\delta)D\ge(1-\delta)e>0$，包含 $Q=0$ 的情况。

### Proof Step 2：精确倒平方根扰动

由 $(1-\delta)D\le E\le(1+\delta)D$ 得
$\sqrt{D/E}\in[(1+\delta)^{-1/2},(1-\delta)^{-1/2}]$。
上偏差精确等于
$\delta/[\sqrt{1-\delta}(1+\sqrt{1-\delta})]$。
分母为 $(1-\delta)+\sqrt{1-\delta}\ge2(1-\delta)$，故上偏差不超过 $h$。
下偏差等于 $\delta/[\sqrt{1+\delta}(1+\sqrt{1+\delta})]\le\delta/2\le h$。
因此 $|E^{-1/2}-D^{-1/2}|\le hD^{-1/2}$，零扰动时同样成立。

### Proof Step 3：近似rsqrt与最终乘法

外部rsqrt律和 Step 2 给出
$|g-D^{-1/2}|\le[(1+\rho)(1+h)-1]D^{-1/2}$，且
$|g|\le(1+\rho)(1+h)D^{-1/2}$。将这两个式子代入
$|\widehat y-y_*|\le u|xg|+\eta+|x||g-D^{-1/2}|$ 得 Claim。
这里允许 $x$ 为负或零；零输入的保守界仍有 $\eta$。

### Proof Step 4：有限范围与外部边界

平方和检查已建立 $R\le R_{\max}$。先检查
$d_{\max}=(1+u)R_{\max}/N+\eta\le F$，再检查
$E_{\max}=(1+u)(d_{\max}+\widehat e)+\eta\le F$，这保证精确操作数在
局部律的有限域内后才使用它。rsqrt契约的输入区间为
$[(1-\delta)e,E_{\max}]$。由于 $D\ge e$，
$D^{-1/2}\le I=\max(1,1/e)$；保守检查
$G=(1+\rho)(1+h)I\le F$ 及 $(1+u)XG+\eta\le F$，从而覆盖rsqrt结果和
最终乘法的有限范围。不通过是unknown，不声称真实执行必然溢出。
有限rsqrt契约是外部前提，本推导未假装从硬件证明其成立。∎

### Open Risks for Output Extension

实际源码/编译器必须对应上述后缀顺序和除数、epsilon值；FMA重排或不同
lowering不能自动继承该结论。真实rsqrt相对误差、除法/乘法误差律仍未验证。
当前参考是理想实数函数，不是仓库float64 fsum/sqrt及float32输出的已执行
reference；后者误差未连接，因此 numeric_contract_checked 继续为false。
