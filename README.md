# VoxClaw

基于 Python 的本地 AI 语音助手，运行于 macOS（Apple Silicon）。

完整链路：**唤醒词检测 (openWakeWord) → 语音活动检测 (Silero VAD) → 语音识别 (Step STT) → AI 对话 (OpenClaw Gateway / Step API) → 语音合成 (Step TTS，支持 WebSocket 流式) → 本地播放**。

## 核心特性

- **多 LLM 后端一键切换**：本地 OpenClaw Gateway、Step API 直连或 DeepSeek API，改 `llm.provider` 即可
- **流式 TTS 低延迟**：WebSocket 边合成边播放，首块音频约 1.6s 出声（HTTP 整段模式可切回）
- **多轮对话**：回答完继续监听追问（默认 10s），无需重复喊唤醒词
- **语音退出指令**：多轮对话中说"退下 / 关闭 / 停止"等词即回待机，指令词可配置
- **DEBUG 手动唤醒**：`--debug` 下可用 `Shift+Control+I` 跳过唤醒词，验证录音、STT、LLM、TTS 链路

## 系统状态机

```
IDLE → (唤醒词) → LISTENING → (开口) → RECORDING → (静音) → THINKING → (回复) → SPEAKING
                      ↑                                                      │
                      │←──────────────── 多轮模式追问 ←────────────────────────┘
                      ↓ (追问超时 / 单轮结束)
                    IDLE
```

## 快速开始

### 1. 环境要求

- macOS（Apple Silicon M 系列）
- Python 3.11+
- 麦克风权限（首次运行时系统会弹窗请求，需授权给终端）

### 2. 安装依赖

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 生成提示音（首次运行前）

```bash
python scripts/generate_assets.py         # 音效版兜底（无需 API Key）
python scripts/generate_voice_assets.py   # 语音版（用 config 中的音色合成，需 step.api_key）
```

语音版提示音内容：

| 文件 | 时机 | 内容 |
| --- | --- | --- |
| greeting.wav | 服务启动 | hi，我是贾维斯，有什么需要随时喊我。 |
| wake.wav | 唤醒/等待追问 | 我在。 |
| error.wav | 识别失败/模型出错 | 我没有听清楚，请重新说一遍。 |
| sleep.wav | 收到退出指令 | 好的，有需要再喊我。 |

改了 `tts.voice` 音色后重新执行 `generate_voice_assets.py` 即可换声。

### 4. 配置

```bash
cp config/config.example.yaml config/config.yaml   # 首次使用先复制模板
```

编辑 `config/config.yaml`：

- `step.api_key`：Step API 密钥（也可用环境变量 `STEP_API_KEY`），用于 STT/TTS
- `llm.provider`：LLM 后端
  - `openclaw`：本地 OpenClaw Gateway（`llm.openclaw.endpoint` 默认 `http://127.0.0.1:18789`，`api_key` 填 gateway.auth.token）
  - `stepfun`：Step API 直连（`api_key` 留空则复用 `step.api_key`）
  - `deepseek`：DeepSeek API（`api_key` 可填 `llm.deepseek.api_key`，也可用环境变量 `DEEPSEEK_API_KEY`）
- `wakeword.model`：唤醒词模型
  - 内置模型名，如 `hey_jarvis`、`alexa`（首次运行自动下载）
  - 或将自训练 `.onnx` 模型放入 `wakeword/hotwords/`，配置文件名如 `hey_kiwi.onnx`

查看音频设备列表：

```bash
python -m audio.device
```

### 5. 运行

```bash
python app.py            # 正常运行
python app.py --debug    # DEBUG 日志 + 手动唤醒热键
python app.py --config 其他配置.yaml
```

启动后对着麦克风说唤醒词（默认 "Hey Jarvis"），听到提示音后说出问题即可。按 `Ctrl+C` 退出。

`--debug` 模式下也可以按 `Shift+Control+I` 手动触发唤醒：程序会跳过 openWakeWord 检测，直接播放唤醒提示音并进入录音，从而验证后续 STT、AI 回复和 TTS。该热键由 `debug.manual_wake_hotkey` 配置；macOS 首次使用全局热键时，可能需要在系统设置的“隐私与安全性 → 辅助功能”中授权当前终端。

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

## TTS 传输模式

由 `config.yaml` 的 `tts.transport` 控制：

```yaml
tts:
  transport: websocket   # websocket=流式低延迟（边合成边播） / http=整段合成后播放
```

流式模式首块音频延迟约 1.6s；如遇音质问题可切回 `http`。

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
| `llm.provider` | openclaw | LLM 后端：openclaw / stepfun / deepseek |
| `llm.deepseek.model` | deepseek-chat | DeepSeek 官方 OpenAI 兼容模型名，可改为 deepseek-reasoner |
| `tts.voice` | wenrounvsheng | 合成音色（wenrounvsheng / cixingnansheng / linjiajiejie 等） |
| `tts.transport` | websocket | TTS 传输：websocket 流式 / http 整段 |

## 常见问题

- **没有声音输入**：检查系统设置 → 隐私与安全性 → 麦克风，确认终端已授权。
- **唤醒词无反应**：`--debug` 查看分数，适当调低 `wakeword.threshold`。
- **手动唤醒热键无反应**：确认使用 `python app.py --debug` 启动，并给终端授权“隐私与安全性 → 辅助功能”。
- **首次启动慢**：openWakeWord 需下载基础模型，属正常现象。
- **LLM 连接失败**：`llm.provider: openclaw` 时需确认本地 Gateway 已启动且开启了 chat completions 接口（`gateway.http.endpoints.chatCompletions.enabled: true`）；也可临时切到 `stepfun` 直连。
