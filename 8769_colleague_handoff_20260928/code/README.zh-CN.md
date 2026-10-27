> Handoff correction: keep this code directory unchanged. Edit the sibling config/runtime.windows-ssh.json. Run from the handoff root using python code/reproduce.py. Keep runtime, virtual environments and outputs outside code/. The full instructions are in START_HERE.zh-CN.md at the handoff root.

# 8769 方法代码整理与复现候选包

现在能够确认的是：**方法提示词、工具和历史代码可以从当前聊天中分离出来；但生成效果脱离本机后是否仍能复现，还没有独立实验支持。** 这份目录是可检查、可准备新实验的 release candidate，不是已经验证完毕的正式 release。

## 这个方法到底做什么

输入是一张物体图片。推理模型先识别可见部件、材质、缝隙、可能的动作，并记录尺度和背面形状等不可见信息的假设。在 native 生成之前，它先用 Blender 建一个可编辑的粗略部件脚手架，用来表达部件关系和预期动作；这个脚手架不是最终外观。

随后将**原图**交给 TRELLIS.2，生成整个物体的 native mesh 与 PBR 材质。固定设置为 `1024_cascade / 24 steps / texture 2048 / seed 42`。保存原始候选、输入哈希、作业回执和渲染，不以旧案例模型代替新生成。

推理模型检查 native 的真实视图，再编写本例的 Blender 细化脚本：确定表面归属、分离可动部件、补必要的厚度和隐藏面、安排铰链轴和父子坐标系，并尽量保留 native 的纹理与细节。这是方法的主要推理和编程环节，**不是现成的通用自动分割函数**。

接着构建 MuJoCo 场景：视觉网格与碰撞网格分开，设置关节、限制、惯量、质量、摩擦及柔性假设。使用 Blender 外部的 Python 跑测试。真实运动必须带动可见表面；只转相机、只动隐藏骨架、只有滑块或能加载 GLB，都不构成正确交互。

最后根据测试和渲染证据进行有限修复，输出 `.blend`、GLB、MJCF/依赖、运动记录、页面和视频。当前整理的 assisted 协议至多两次物理/视觉验收和两轮修复；失败后可以保留可用候选，但必须写成 `failed/partial/kinematic`，不能算物理通过。

## 三种东西不要混淆

| 名称 | 实际内容 | 与历史结果关系 |
|---|---|---|
| 原始 `trellis2-native-refine` 1.2.0 | 技能文本、native 客户端、API 执行适配器 | 原版快照单独保存在历史源码包中；不是后续所有实验的同一入口 |
| 8769 assisted 20260923 | 原版建模流程 + 完整 worker prompt + 明示的历史代码参考 + 本地订阅执行 | Figure 8 14 例、Appearance20 20 例采用此类协议；`strict_isolation=false` |
| 8794 General Agent Loop | 后续 Planner/Reviewer/Builder 等通用控制器及多次版本演进 | 50 例展示跨多个版本，有 continuation、generation-only 和额外人工处理 |

本目录选定 **Figure 8 的 assisted 协议**作为可迁移入口，因为它的完整提示词、参考代码、输入和结果记录可以明确对应。没有把它冒充为一个全新的无参考代码算法。新启动器不自动带入当前聊天，也不读取旧结果；但代码参考本身属于已经声明的方法内容。

## 文件与启动

完整英文 quick start 见根目录 README.md。先运行 `python reproduce.py verify`，再填写代码目录外的 `../config/runtime.windows-ssh.json`，按 doctor → prepare → plan → run 执行。

代码准备和检查不消耗生成额度；`run` 才启动推理模型。它需要接收者自己的登录，不传递我们的账号、不复制凭据、不切换为 API 计费。模型不可用、CLI 缺少必要参数、环境不通或权限被拒时，应该停止并记录，不静默降级。

`prepare` 的产物是一个带清单的新实验目录，不是沙箱。正式测“离开当前会话能否复现”时，必须将该目录放入干净、独立验证过的系统环境；不要在现有工作目录直接生成后就宣称隔离复现。

## 目前验证到哪一步

- 历史源码与各自冻结清单逐文件核对，结果在主交付目录 `audit/source_integrity.json`。
- 新启动器的校验、独立目录准备、固定参数、拒绝覆盖及输入哈希行为有离线测试。
- 本次没有启动新的资产生成、没有修改已安装技能、没有重新跑物理验收。
- 新启动器与原始批处理器并不完全等同：不自动重试/恢复会话，使用一次完整 worker turn 和显式墙钟预算。它是**另行命名的适配器**，需要新机器测试后才能继承质量结论。
- 历史主模型与 native 代码文件哈希已纳入；当前远端 SSH 超时，未重新核验全部服务器环境，DINO/BiRefNet 完整权重清单仍需补齐。

请优先阅读 `docs/CONTEXT_AUDIT.zh-CN.md` 和 `docs/REPRODUCTION.zh-CN.md`。正式 release 的关键门槛是“同一公开协议在干净机器上重新生成并按同一标准评估”，而不是仅能下载源码、启动 CLI 或播放旧视频。
