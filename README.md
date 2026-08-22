# VoxClaw

基于 Python 的本地 AI 语音助手，支持 macOS 与 Windows。

完整链路：**唤醒词检测 (openWakeWord) → 语音活动检测 (Silero VAD) → 语音识别 (腾讯云 ASR / Step STT) → AI 对话 (OpenClaw Gateway / Step API / 智谱 AI) → 语音合成 (Step TTS / 科大讯飞 TTS) → 本地播放**。

## 核心特性

- **多 LLM 后端一键切换**：本地 OpenClaw Gateway、Step API、DeepSeek 或智谱 AI，改 `llm.provider` 即可
- **多 STT 服务商**：可选择 Step STT 或腾讯云语音识别；腾讯云 ASR 每日有免费额度
- **多 TTS 服务商**：可选择 Step TTS 或科大讯飞 TTS；两者都支持流式播放，讯飞可使用每日免费额度
- **多轮对话**：回答完继续监听追问（默认 10s），无需重复喊唤醒词
- **语音退出指令**：多轮对话中说"退下 / 关闭 / 停止"等词即回待机，指令词可配置
- **DEBUG 手动唤醒**：`--debug` 下可用 `Shift+Control+I` 跳过唤醒词，验证录音、STT、LLM、TTS 链路
- **本地日历时间**：不用联网即可回答今天星期几、明天几号、下周一是几号、现在几点等问题
- **本地定时提醒**：支持多个提醒、取消提醒，提醒到点后自动语音播报
- **实时天气查询**：通过豆包搜索或 Tavily 搜索最新天气信息，再由 LLM 总结成适合语音播报的回答

## 系统状态机

```
IDLE → (唤醒词) → LISTENING → (开口) → RECORDING → (静音) → THINKING → (回复) → SPEAKING
                      ↑                                                      │
                      │←──────────────── 多轮模式追问 ←────────────────────────┘
                      ↓ (追问超时 / 单轮结束)
                    IDLE
```

## 平台支持

| 平台 | 支持状态 | 说明 |
| --- | --- | --- |
| macOS | 支持 | 推荐 Apple Silicon + Python 3.11；首次运行需授权麦克风，DEBUG 热键需授权辅助功能。 |
| Windows | 支持 | 推荐 Windows 10/11 + Python 3.11；需允许桌面应用访问麦克风。 |

音频采集/播放使用 `sounddevice` + PortAudio，唤醒词和 VAD 使用 ONNX 推理，因此代码不绑定某个系统。不同平台主要差异在音频设备名称、权限设置和全局热键占用。

## 快速开始

### 1. 环境要求

- Python 3.11+
- 可用麦克风与扬声器/耳机
- 网络访问 Step / 智谱 AI / 科大讯飞 / DeepSeek / OpenClaw / 豆包搜索等接口
- macOS：系统设置 → 隐私与安全性 → 麦克风，允许当前终端访问；DEBUG 热键还需“辅助功能”权限
- Windows：设置 → 隐私和安全性 → 麦克风，开启“麦克风访问权限”和“允许桌面应用访问麦克风”

### 2. 安装依赖

macOS Terminal：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

如果 PowerShell 阻止激活脚本，可先执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 3. 配置

```bash
cp config/config.example.yaml config/config.yaml   # 首次使用先复制模板
```

Windows PowerShell：

```powershell
Copy-Item config\config.example.yaml config\config.yaml
```

编辑 `config/config.yaml`：

- `stt.provider`：STT 服务商，可选 `step` / `tencent`；使用腾讯云时配置 `stt.tencent.secret_id` 和 `stt.tencent.secret_key`
- `tts.provider`：TTS 服务商，可选 `step` / `xfyun`；使用讯飞时配置 `tts.xfyun.app_id`、`tts.xfyun.api_key`、`tts.xfyun.api_secret`
- `prompts.system`：LLM 系统提示词，用于控制助手人设、回答风格和长度
- `prompts.voice_assets`：提示音生成文案，修改后需重新运行 `python scripts/generate_voice_assets.py`，脚本会跟随 `tts.provider` 使用 Step 或讯飞生成
- `calendar.timezone`：本地日历/时间工具使用的时区，例如 `Asia/Shanghai`
- `reminder.storage_path`：本地提醒保存文件，默认 `data/reminders.json`，重启后未到期提醒仍会保留
- `doubao_search.api_key`：豆包搜索 API Key，也可用环境变量 `DOUBAO_SEARCH_API_KEY` 或 `VOLCENGINE_SEARCH_API_KEY`；国内网络建议优先使用
- `tavily.api_key`：Tavily API Key，也可用环境变量 `TAVILY_API_KEY`；可作为备用搜索源
- `weather.default_location`：默认天气位置，用户没说地点时使用，例如 `上海松江`
- `llm.provider`：LLM 后端
  - `openclaw`：本地 OpenClaw Gateway（`llm.openclaw.endpoint` 默认 `http://127.0.0.1:18789`，`api_key` 填 gateway.auth.token）
  - `stepfun`：Step API 直连（需要填写 `llm.stepfun.api_key`）
  - `deepseek`：DeepSeek API（`api_key` 可填 `llm.deepseek.api_key`，也可用环境变量 `DEEPSEEK_API_KEY`）
  - `zhipu`：智谱 AI（`glm-4-flash` / `glm-4.7-flash`，可用环境变量 `ZHIPU_API_KEY` 或 `BIGMODEL_API_KEY`）

智谱环境变量示例：

```bash
export ZHIPU_API_KEY=你的Key
```

Windows PowerShell：

```powershell
$env:ZHIPU_API_KEY="你的Key"
```

- `wakeword.model`：唤醒词模型
  - 内置模型名，如 `hey_jarvis`、`alexa`（首次运行自动下载）
  - 或将自训练 `.onnx` 模型放入 `wakeword/hotwords/`，配置文件名如 `hey_kiwi.onnx`

查看音频设备列表：

```bash
python -m audio.device
```

Windows 上如果默认设备不可用，可将输出里的设备编号填入 `audio.input_device` / `audio.output_device`。

### 服务开通说明

项目会用到 LLM、TTS、搜索等外部服务。个人使用建议优先选择有免费额度的服务，并尽量通过环境变量保存密钥，避免把 Key 提交到仓库。

- **智谱 AI GLM-4-Flash**：强烈推荐，`glm-4-flash` / `glm-4.7-flash` 可作为免费 LLM 后端。申请步骤参考：<https://www.doubao.com/thread/xlbFYe8qIR5B2xfYN>
- **腾讯云语音识别 ASR**：用于 STT 语音识别，一句话识别适合语音助手短句输入，每日有免费额度。申请步骤参考：<https://www.doubao.com/thread/xJkEYdCc5IPRhXk>
- **科大讯飞 TTS**：注册并实名认证后，在线语音合成通常有每日免费额度，可作为默认语音播报服务。申请步骤参考：<https://www.doubao.com/thread/xCjTOq1WOFXLJwaG0>
- **火山引擎豆包搜索**：用于联网天气/实时信息查询，适合国内网络环境，个人免费额度通常够日常使用。开通步骤参考：<https://www.doubao.com/thread/xJuCsw3oGmHhgKiCS>
- **DeepSeek API**：需要先充值或开通付费后 API Key 才能正常调用。申请入口：<https://platform.deepseek.com/api_keys>

### 4. 生成提示音（首次运行前）

```bash
python scripts/generate_assets.py         # 音效版兜底（无需 API Key）
python scripts/generate_voice_assets.py   # 语音版（用 config 中的 TTS 服务、音色和文案合成）
```

语音版提示音内容由 `config.yaml` 的 `prompts.voice_assets` 控制：

| 文件 | 时机 | 内容 |
| --- | --- | --- |
| greeting.wav | 服务启动 | hi，我是贾维斯，有什么需要随时喊我。 |
| wake.wav | 唤醒/等待追问 | 我在。 |
| error.wav | 识别失败/模型出错 | 我没有听清楚，请重新说一遍。 |
| sleep.wav | 收到退出指令 | 好的，有需要再喊我。 |

改了 `tts.step.voice`、`tts.xfyun.voice` 或 `prompts.voice_assets` 文案后，重新执行 `generate_voice_assets.py` 即可更新提示音。

### 5. 运行

```bash
python app.py            # 正常运行
python app.py --debug    # DEBUG 日志 + 手动唤醒热键
python app.py --config 其他配置.yaml
```

启动后对着麦克风说唤醒词（默认 "Hey Jarvis"），听到提示音后说出问题即可。按 `Ctrl+C` 退出。

`--debug` 模式下也可以按 `Shift+Control+I` 手动触发唤醒：程序会跳过 openWakeWord 检测，直接播放唤醒提示音并进入录音，从而验证后续 STT、AI 回复和 TTS。该热键由 `debug.manual_wake_hotkey` 配置；macOS 首次使用全局热键时，可能需要在系统设置的“隐私与安全性 → 辅助功能”中授权当前终端。Windows 如遇热键冲突，可改为 `<ctrl>+<alt>+i`。

## 本地日历时间

日期、星期和当前时间问题会优先走本地工具，不依赖联网和大模型知识，因此响应快且稳定。

支持示例：

- “今天星期几？”
- “明天星期几？”
- “今天几号？”
- “后天几号？”
- “后天是星期几？”
- “下个星期一是几号？”
- “下周一是几号？”
- “本周五是几号？”
- “上周日是几号？”
- “现在几点了？”
- “今天是什么日子？”
- “这个月有多少天？”
- “二月有多少天？”

配置方式：

```yaml
calendar:
  enabled: true
  timezone: Asia/Shanghai
```

## 本地定时提醒

提醒会在本地解析和保存，不依赖联网；同一时间可以设置多个提醒，重启后未到期提醒会从 `data/reminders.json` 恢复。

支持示例：

- “十分钟后叫我”
- “十五分钟之后提醒我喝水”
- “再过十分钟后提醒我”
- “5分钟后喊我”
- “半小时后提醒我喝水”
- “下午三点半提醒我喝水”
- “明天早上八点叫我”
- “十二点的时候喊我”
- “查询提醒”
- “现在有哪些任务？”
- “我还有几个提醒？”
- “取消提醒”
- “取消所有提醒”

设置成功后会播报类似“好的，我将在十分钟后提醒你”或“好的，我会在今天十二点提醒你”。创建提醒时会让 LLM 把口语化内容提炼成短事项，例如“我需要开会记得我”会保存为“开会”。查询时会播报当前待触发提醒列表，例如“你现在有2个提醒。第一个，今天六点提醒你：喝水”。到点后会播报“时间到了，我来提醒你了”或带上具体事项。说“取消提醒”会取消最近一个待触发提醒，说“取消所有提醒”会清空全部待触发提醒。

配置方式：

```yaml
reminder:
  enabled: true
  timezone: Asia/Shanghai
  storage_path: data/reminders.json
  check_interval_s: 1.0
```

## 实时天气查询

天气问题会优先走工具层：VoxClaw 使用豆包搜索或 Tavily 搜索最新天气网页信息，再让当前 LLM 总结成口语化回答。国内网络环境建议使用豆包搜索，Tavily 可作为备用。

支持示例：

- “今天天气怎么样？”
- “现在多少度？”
- “下午会下雨吗？”
- “需要带伞吗？”
- “明天上海松江是什么天气？”
- “后天下午会下雨吗？”
- “最近几天会不会降温？”

天气工具会把“今天上午 / 今天下午 / 明天 / 后天 / 大后天 / 最近几天”等相对时间解析成明确日期和时段，再用这些信息搜索天气。若搜索结果只查到全天预报、没有分时段数据，助手会说明分时段信息不够完整，避免编造。

配置方式：

```yaml
tools:
  enabled: true

tavily:
  enabled: true         # 备用搜索源
  api_key: ""          # 推荐用环境变量 TAVILY_API_KEY
  search_depth: basic  # basic 更快更省额度
  max_results: 5

doubao_search:
  enabled: true
  api_key: ""          # 推荐用环境变量 DOUBAO_SEARCH_API_KEY 或 VOLCENGINE_SEARCH_API_KEY
  endpoint: https://open.feedcoopapi.com/search_api/global_search
  doc_count: 5
  max_snippet_length: 500

weather:
  enabled: true
  provider: doubao     # 可选 doubao / tavily
  default_location: 上海松江
  timezone: Asia/Shanghai
```

如果没有配置所选 provider 对应的 API Key，命中天气问题时会提示未配置天气查询服务。豆包搜索环境变量：

```bash
export DOUBAO_SEARCH_API_KEY=你的Key
```

Windows PowerShell：

```powershell
$env:DOUBAO_SEARCH_API_KEY="你的Key"
```

Tavily 备用环境变量：

```bash
export TAVILY_API_KEY=你的Key
```

Windows PowerShell：

```powershell
$env:TAVILY_API_KEY="你的Key"
```

## Windows 使用指南

1. 使用 PowerShell 安装依赖并复制 `config/config.example.yaml` 到 `config/config.yaml`。
2. 在 Windows 设置中允许桌面应用访问麦克风。
3. 运行 `python -m audio.device`，确认存在输入/输出设备；如默认设备不对，把设备编号写入配置：

```yaml
audio:
  input_device: 1
  output_device: 3
```

4. 先运行 `python scripts/generate_assets.py` 生成无需 API Key 的兜底提示音。
5. 运行 `python app.py --debug`，先用 `Shift+Control+I` 手动唤醒验证录音、STT、LLM、TTS 链路。
6. 如果唤醒词不灵敏，运行 `python scripts/test_wakeword.py` 查看分数，并调整 `wakeword.threshold`。

Windows 常见音频后端是 WASAPI / MME / DirectSound，推荐优先使用系统默认设备；如果蓝牙耳机同时提供“耳机”和“免提”设备，建议选择独立麦克风或免提输入，避免采样率和占用冲突。

## macOS 使用指南

1. 使用 Terminal/iTerm 安装依赖并复制配置文件。
2. 首次启动时授权麦克风权限；如使用 `--debug` 手动唤醒，再授权“辅助功能”。
3. 运行 `python -m audio.device` 查看设备；如外接声卡/麦克风没有被默认选中，把设备编号写入 `audio.input_device` / `audio.output_device`。
4. Apple Silicon 上如个别依赖安装异常，确认使用原生 arm64 Python 3.11，而不是 Rosetta 下的 x86_64 Python。

## 对话模式

由 `config.yaml` 的 `conversation:` 段控制：

```yaml
conversation:
  mode: multi              # single=单轮（答完回待机）/ multi=多轮（答完继续听追问）
  follow_up_timeout_s: 10.0  # 多轮模式下等待追问的时长，超时回待机
  exit_words: ["关闭", "退下", "关机", "停止", "退出", "再见", "闭嘴", "休眠"]
```

- **单轮模式（single）**：每次对话都需要唤醒词，回答完立即回待机。
- **多轮模式（multi）**：回答播放完会再次响提示音并继续聆听，`follow_up_timeout_s` 秒内直接说话即可追问；超时未说话则回待机。
- **退出指令（exit_words）**：识别文本完全等于指令词（如"退下"），或不超过 6 个字的短句包含指令词（如"好了退下吧"）时，播放休眠提示音并回待机；长句不受影响（如"帮我关闭客厅的灯"会正常送给 AI）。环境杂音触发误录音时，说一声"停止"即可结束对话。

## STT 服务商

由 `config.yaml` 的 `stt.provider` 控制语音识别服务：

```yaml
stt:
  provider: tencent      # step=阶跃星辰 / tencent=腾讯云语音识别
  step:
    api_key: ""          # 推荐使用环境变量 STEP_API_KEY
    stt_model: step-asr
  tencent:
    secret_id: ""        # 推荐使用环境变量 TENCENT_SECRET_ID
    secret_key: ""       # 推荐使用环境变量 TENCENT_SECRET_KEY
    engine_model_type: 16k_zh
    voice_format: wav
```

腾讯云环境变量示例：

```bash
export TENCENT_SECRET_ID=你的SecretId
export TENCENT_SECRET_KEY=你的SecretKey
```

Windows PowerShell：

```powershell
$env:TENCENT_SECRET_ID="你的SecretId"
$env:TENCENT_SECRET_KEY="你的SecretKey"
```

启动日志会打印当前使用的 STT 服务，例如 `STT 使用腾讯云服务` 或 `STT 使用 Step 服务`。

## TTS 服务商

由 `config.yaml` 的 `tts.provider` 控制语音合成服务：

```yaml
tts:
  provider: step         # step=阶跃星辰 / xfyun=科大讯飞
  step:
    voice: linjiajiejie  # Step 音色
    speed: 1.2
    transport: websocket # websocket=流式低延迟 / http=整段合成
  xfyun:
    app_id: ""           # 推荐使用环境变量 XFYUN_APP_ID
    api_key: ""          # 推荐使用环境变量 XFYUN_API_KEY
    api_secret: ""       # 推荐使用环境变量 XFYUN_API_SECRET
    voice: x4_yezi       # 讯飞发音人，可在控制台查看
    speed: 50            # 0-100，50 为默认
    volume: 50
    pitch: 50
```

Step 的 WebSocket 流式模式首块音频延迟约 1.6s；如遇音质问题可切回 `http`。讯飞使用 WebAPI WebSocket 流式返回音频，收到首块音频后立即播放，优点是可使用讯飞每日免费额度。启动日志会打印当前使用的 TTS 服务。

讯飞环境变量示例：

```bash
export XFYUN_APP_ID=你的AppID
export XFYUN_API_KEY=你的APIKey
export XFYUN_API_SECRET=你的APISecret
```

Windows PowerShell：

```powershell
$env:XFYUN_APP_ID="你的AppID"
$env:XFYUN_API_KEY="你的APIKey"
$env:XFYUN_API_SECRET="你的APISecret"
```

## 目录结构

```
voxclaw/
├── app.py                  # 程序入口
├── config/                 # 配置（YAML + pydantic）
├── audio/                  # 麦克风采集 / 播放 / 环形缓冲 / 设备管理
├── wakeword/               # openWakeWord 唤醒词检测（hotwords/ 放自训练模型）
├── vad/                    # Silero VAD（onnxruntime 推理，无 torch 依赖）
├── stt/                    # Step 语音识别客户端
├── llm/                    # LLM 客户端（OpenAI 兼容，OpenClaw Gateway / Step 直连）
├── tts/                    # Step 语音合成客户端（HTTP + WebSocket 流式）
├── assistant/              # 主管线 / 会话 / 状态机
├── utils/                  # 日志 / 计时 / 音频 / 文本清理工具
├── assets/                 # 提示音（greeting / wake / thinking / error / sleep）
└── scripts/                # 辅助脚本
```

## 关键配置项

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `audio.sample_rate` | 16000 | 采样率（唤醒词与 VAD 模型要求 16kHz） |
| `audio.block_size` | 512 | 采集块大小（与 Silero VAD 输入块对齐） |
| `wakeword.threshold` | 0.45 | 唤醒词置信度阈值，误唤醒多则调高 |
| `vad.threshold` | 0.55 | 语音概率阈值 |
| `vad.silence_ms` | 500 | 静音多久判定说话结束 |
| `vad.speech_timeout_s` | 6.0 | 唤醒后等待开口的超时 |
| `vad.max_record_s` | 15.0 | 单次录音上限 |
| `conversation.mode` | multi | 单轮 / 多轮对话 |
| `conversation.follow_up_timeout_s` | 10.0 | 多轮模式等待追问时长 |
| `conversation.exit_words` | 关闭/退下/停止... | 语音退出指令词列表 |
| `debug.manual_wake_hotkey` | `<shift>+<ctrl>+i` | `--debug` 模式下跳过唤醒词的手动唤醒热键 |
| `stt.provider` | tencent | STT 服务商：step / tencent |
| `stt.step.stt_model` | step-asr | Step STT 模型名 |
| `stt.tencent.engine_model_type` | 16k_zh | 腾讯云 ASR 识别引擎，适合 16k 中文普通话 |
| `prompts.system` | VoxClaw 语音助手... | LLM 系统提示词 |
| `prompts.voice_assets.*` | greeting/wake/error/sleep | 提示音生成文案 |
| `tools.enabled` | true | 是否启用工具层 |
| `calendar.timezone` | Asia/Shanghai | 本地日历/时间工具使用的时区 |
| `reminder.enabled` | true | 是否启用本地定时提醒工具 |
| `reminder.timezone` | Asia/Shanghai | 解析提醒时间时使用的时区 |
| `reminder.storage_path` | data/reminders.json | 待触发提醒持久化文件 |
| `reminder.check_interval_s` | 1.0 | 后台检查提醒是否到期的间隔秒数 |
| `doubao_search.api_key` | 空 | 豆包搜索 API Key，也可用环境变量 `DOUBAO_SEARCH_API_KEY` |
| `tavily.api_key` | 空 | Tavily API Key，也可用环境变量 `TAVILY_API_KEY` |
| `weather.provider` | doubao | 天气搜索源：doubao / tavily |
| `weather.default_location` | 上海松江 | 天气查询默认位置 |
| `llm.provider` | zhipu | LLM 后端：openclaw / stepfun / deepseek / zhipu |
| `llm.deepseek.model` | deepseek-chat | DeepSeek 官方 OpenAI 兼容模型名，可改为 deepseek-reasoner |
| `llm.zhipu.model` | glm-4-flash | 智谱免费模型，可改为 glm-4.7-flash |
| `tts.provider` | step | TTS 服务商：step / xfyun |
| `tts.step.tts_model` | step-tts-mini | Step TTS 模型名 |
| `tts.step.voice` | linjiajiejie | Step 合成音色（wenrounvsheng / cixingnansheng / linjiajiejie 等） |
| `tts.step.transport` | websocket | Step TTS 传输：websocket 流式 / http 整段 |
| `tts.xfyun.voice` | x4_yezi | 科大讯飞发音人，`tts.provider: xfyun` 时使用 |
| `tts.xfyun.speed` | 50 | 科大讯飞语速，通常 0-100 |

## 常见问题

- **没有声音输入**：macOS 检查“隐私与安全性 → 麦克风”；Windows 检查“隐私和安全性 → 麦克风”并允许桌面应用访问。
- **音频设备选错**：运行 `python -m audio.device`，把正确设备编号填到 `audio.input_device` / `audio.output_device`。
- **唤醒词无反应**：`--debug` 查看分数，适当调低 `wakeword.threshold`。
- **手动唤醒热键无反应**：确认使用 `python app.py --debug` 启动；macOS 给终端授权“辅助功能”，Windows 可把热键改成 `<ctrl>+<alt>+i`。
- **天气查询不可用**：确认 `weather.provider` 对应的搜索源已启用，并配置 `DOUBAO_SEARCH_API_KEY` / `VOLCENGINE_SEARCH_API_KEY` 或 `TAVILY_API_KEY`。
- **Windows 依赖安装失败**：确认使用 Python 3.11 64-bit，并先升级 `pip`；不要复用 macOS 下的 `.venv`。
- **首次启动慢**：openWakeWord 需下载基础模型，属正常现象。
- **LLM 连接失败**：`llm.provider: openclaw` 时需确认本地 Gateway 已启动且开启了 chat completions 接口（`gateway.http.endpoints.chatCompletions.enabled: true`）；也可临时切到 `stepfun` 直连。
