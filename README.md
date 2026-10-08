# clef-mcp

[Cloudflare Clef](https://huggingface.co/Cloudflare/clef)([Ollama](https://ollama.com/library/clef) ホスト版)を Claude Code から使えるようにする **MCP サーバ**。

Clef は Jev / System One API 互換の**判断モデル**で、`state`(状態)+ 型付き質問(`noul` / `choice` / `score`)を受け取り、確率・信頼度付きの**型付き決定**を文章生成なしに返します。このサーバは Ollama の `POST /v1/systemone` をラップし、Claude Code からツール1つで判断を依頼できるようにします。

```
Claude Code ──(MCP stdio)──> clef-mcp ──(HTTP)──> Ollama /v1/systemone ──> clef (27B / clef-flash 9B)
```

## 提供するツール

| ツール | 説明 |
|---|---|
| `decide(state, questions)` | System One 形式で判断を依頼。`state` は文字列 / JSONオブジェクト / 配列。`questions` は id → `{type, instructions, criteria}`(最大64問) |
| `health()` | Ollama への到達性・バージョン・現在のコネクション設定を JSON で返す |

## 必要条件

- Ollama(`decision` 対応ビルド、0.35 系で動作確認済み)に `clef`(または `clef-flash`)が導入済み
  ```bash
  ollama pull clef   # 27B、約17GB
  ```
- Python 3.10+
- Claude Code

> **別ホストの Ollama を使う場合**:Ollama サーバがあるマシンのアドレス(NetBird / Tailscale / LAN いずれも可)を `CLEF_BASE_URL` で指定します。

## インストール

```bash
git clone https://github.com/kanedayo/clef-mcp.git
cd clef-mcp
./install.sh                        # venv 作成 + 依存インストール
CLEF_BASE_URL=http://<ollamaホスト>:11434 ./install.sh --register   # Claude Code への登録も実行
```

### 手動で登録する場合

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

claude mcp add clef -s user \
  -e CLEF_BASE_URL=http://<ollamaホスト>:11434 \
  -- "$(pwd)/.venv/bin/python" "$(pwd)/clef_mcp.py"

claude mcp list   # clef: ... - ✔ Connected を確認
```

## 設定(環境変数)

| 変数 | デフォルト | 説明 |
|---|---|---|
| `CLEF_BASE_URL` | `http://$OLLAMA_HOST`(未設定なら `http://localhost:11434`) | Ollama のベースURL |
| `CLEF_MODEL` | `clef` | モデル名。`clef-flash` 等にも切替可 |
| `CLEF_TIMEOUT` | `180` | リクエストタイムアウト(秒)。初回はモデルロードで時間がかかる |

## 使い方

Claude Code の**セッションを再起動**するとツールが読み込まれます。以降は自然言語で:

> 「このPRの差分を clef でレビューして、マージ可否・リスクレベル・影響範囲を判定して」

Claude Code が差分を `state` に整形して `mcp__clef__decide` を呼び、確率付きの結果を解釈して報告します。

応答の例:

```json
{
  "answers": {
    "merge_safe": { "type": "noul",  "noul": 0.978 },
    "risk_level": { "type": "score", "score": 1.02,
                    "probabilities": { "0": 0.076, "1": 0.844, "2": 0.067, "3": 0.013 } },
    "area":       { "type": "choice", "choice": "ui",
                    "probabilities": { "ui": 0.988, "payments": 0.006, "infra": 0.006 } }
  },
  "usage": { "input_tokens": 376, "output_tokens": 0 }
}
```

**役割分担の原則**: 生成と推論は Claude に残し、**「高頻度・二択〜数択・高速でいい」判断**(分類・トリアージ・マージリスク・意図検出・出力チェック)だけ clef に分流させます。

## トラブルシュート

- **`model "clef" not found`** → `CLEF_BASE_URL` が指す Ollama に clef がありません。`ollama list` の出たインスタンス(環境変数 `OLLAMA_HOST` があるとそちらを参照します)と一致させてください。
- **初回リクエストが遅い/タイムアウト** → モデル(約17GB)のロード中です。そのまま再試行してください。
- **`No module named 'mcp.server.fastmcp'`** → `mcp` SDK 2.x が入っています。`requirements.txt` 通り `mcp<2` にしてください。

## 使用例の詳細

判断モデルの実用例(品質ゲート検証、ピクセルから操作するゲームAI、確率較正ベンチ等)は [USECASES.md](./USECASES.md) を参照してください。

## License

[Apache-2.0](./LICENSE)
