> Handoff correction: keep this code directory unchanged. Edit the sibling config/runtime.windows-ssh.json. Run from the handoff root using python code/reproduce.py. Keep runtime, virtual environments and outputs outside code/. The full instructions are in START_HERE.zh-CN.md at the handoff root.

# 外部机器复现实验操作说明

## 1. 固定目标环境

先用 Windows 11 作控制机，Linux 作 TRELLIS.2 生成机。这样最接近历史部署，减少同时更换操作系统、模型入口、物理库和 Blender API 带来的干扰。两者可以是接收者自行准备的独立机器/虚拟机。完全 Linux 的控制器配置另附，但目前仅是待验证模板，不作为已通过平台。

历史控制端记录：Python 3.12.10、Blender 5.2.1 LTS、gpt-6-astra/high、ChatGPT subscription；historical CLI 需与发布者的实际记录比对，当前审计机为 `0.158.0-alpha.2.1`，不能把当前版本误称为历史运行版本。`requirements.observed.txt` 是当前已安装依赖清单，不是经过新机器重装检验的完整锁文件。

历史 native 端记录：Python 3.10.21、PyTorch 2.6.0+cu124；使用 TRELLIS.2-4B、DINOv3 和 BiRefNet。TRELLIS 官方目前只声明 Linux 测试环境，要求 NVIDIA GPU 至少 24GB，并建议 CUDA 12.4；本地客户端历史 minimum-free 设置是 28GB，不应将官方最低值直接视为此流程的充足配置。安装参考：https://github.com/microsoft/TRELLIS.2 。最终应以冻结权重、依赖、native doctor 和真实 1024 推理结果为准。

不要将当前 `main` 随意当成历史 native runtime。`provenance/remote_runtime_sha256.txt`、`remote_model_sha256.txt` 是 2026-09-23 已记录的文件哈希。用 `verify_external.py` 在你的部署根目录比较。缺少源文件/权重、文件有修改或依赖不同，应明确记为环境偏差。

## 2. 安装并配置

1. 在全新的控制系统中安装你自己的 Python、Blender、Codex CLI 并登录你自己的账号；确认指定模型可用。不要拷贝发布者的 `.codex`、用户目录、SSH 私钥或登录文件。
2. 在 Linux 安装独立的 TRELLIS runtime 和权重。若使用 SSH，按正常方式配置你自己的主机别名和主机指纹。代码保留主机验证，不要求关闭 StrictHostKeyChecking。
3. 将 `examples/runtime.windows-ssh.json` 复制到代码目录外（交接包已提供 `../config/runtime.windows-ssh.json`）作为本地 runtime 配置，填入 Python/Blender/CLI 和服务器目录。配置只包含路径和参数，不放密钥。
4. `python reproduce.py verify` 核对代码；执行 doctor 与 `doctor --native`。普通 doctor 不验证账号模型可用性，也不验证资产质量。

## 3. 准备并生成

在结果目录之外运行：

```text
python reproduce.py prepare --image INPUT.png --config runtime.json --out C:/experiments/replica_001
python reproduce.py plan C:/experiments/replica_001
python reproduce.py run C:/experiments/replica_001
```

准备后先检查 `identity.json`、`prompt.md` 和 `runtime.json`。只允许输入图片、该固定方法、明确配置和本例新产物。历史报告、展示视频、旧 `.blend`、旧 native、当前聊天内容与人工个案指导均不放入这个运行环境。保留完整 worker 事件流、错误与生成脚本，不能只保存成功截图。

已有目录或已执行过的 run 不会自动覆盖。失败后请先记录结果；若决定重试，使用新编号，保留尝试次数与失败原因。CLI 参数缺失、权限拒绝、模型不可用或网络失败，不应改为绕过权限来“跑通”。

新 launcher 的墙钟预算含等待，不复刻旧批处理容量排队/续跑策略。这是当前候选版本的明确差异；如果要复现旧调度策略，应在独立命名版本实现并再次冻结测试。

## 4. 两种测试分开做

**软件/播放复现**：复制已有资产，在新机器上能加载、渲染、播放；这只能验证文件及渲染环境。

**生成效果复现**：只给新机器原图、公开方法和配置，从新 native 开始重做。比较新旧结果的外观、部件分割、关节连接、可见运动和物理记录。后者才回答用户现在关心的问题。

建议先按随结果目录给出的 `reproduction_plan.json` 做 6 个固定抽样案例，每例 3 次完整生成，用于检查环境和波动；再扩展到全部 34 个原始 assisted 输入。6 例由固定随机种子从 34 例中抽样，不按成功程度挑选。小样本试运行通过并不等价于证明全体成功率。

TRELLIS seed 固定为 42 只是一个控制变量；推理模型采样、GPU/CUDA、扩展算子和 Blender 版本仍可能产生不同结果。评估应报告质量和成功率分布，不承诺逐字节相同资产。

## 5. 预登记评价内容

- 输入与方法哈希一致；全新 native 回执且不复用旧模型。
- native → refined 的外观对照：颜色、轮廓、纹理与细节是否保留，必须读实际像素。
- 逐关节检查静止、中间、端点：正确部件随正确关节运动，有无飞散、错误旋转中心、断开、穿透。位移应结合本体尺度与该动作语义评估，不以一个通用固定距离替代检查。
- 柔性表面必须有真实绑定证据；刚性替代、近似形变和缺失分别记录。
- 真实执行物理测试，保存所用场景、轨迹和测量。历史 `passed` 只是当时声明范围内通过，不覆盖所有接触/载荷/拓扑。
- 保留失败、部分完成、转台、超时、网络和人工干预；成功率分母是所有已启动实验。
- 将新结果与历史结果分开目录；验收者可读两边，生成 worker 不可读历史结果。

没有独立执行上述实验之前，release 状态保持 `reproduction_not_yet_demonstrated`。
