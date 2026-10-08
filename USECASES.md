# Clef 使用例まとめ

> Cloudflare **Clef** は 2026年10月1日に公開された**オープンソース(Apache-2.0)の判断モデル**。「状態(state) + 型付き質問」を受け取り、確率・信頼度付きの**型付き決定**を文章生成なしに返す、Jev / System One API 互換モデルです。
>
> - `clef`(27B、Qwen3.8-27B ベース) / `clef-flash`(9B、Qwen3.5-9B ベース)
> - 入力はテキスト / JSON / 画像 / 動画(Jev はテキストのみ)
> - 質問タイプは `noul`(0–1 の真偽) / `choice`(選択肢) / `score`(順序採点)、1リクエスト最大64問
> - Workers AI 料金:入力 $0.24/1M(27B)・$0.09/1M(flash)。中央値レイテンシ ~209ms(27B) / ~39ms(flash)※いずれも自社報告値

---

## 1. 使い方(基本)

### Ollama でローカル/セルフホスト運用

```bash
ollama pull clef        # 27B、約17GB
ollama serve            # http://localhost:11434
```

Ollama は判断モデル向けに **`POST /v1/systemone`** をネイティブ提供します:

```bash
curl -s http://localhost:11434/v1/systemone \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "clef",
    "state": {
      "diff_summary": "Add a null check before calling user.profile.name",
      "test_status": "34/34 passing"
    },
    "questions": {
      "merge_safe": {
        "type": "noul",
        "instructions": "Is this diff safe to merge?"
      },
      "risk_level": {
        "type": "score",
        "instructions": "Risk level of this change",
        "criteria": ["None - cosmetic", "Low - additive and test-covered",
                     "Medium - touches core logic", "High - auth/billing/migration"]
      },
      "area": {
        "type": "choice",
        "instructions": "Which area does this change primarily affect?",
        "criteria": { "payments": "billing code", "ui": "frontend",
                      "infra": "config/infra" }
      }
    }
  }'
```

応答(実測例):

```json
{
  "model": "clef",
  "answers": {
    "merge_safe": { "type": "noul",  "noul": 0.978 },
    "risk_level": { "type": "score", "score": 1.02,
                    "probabilities": { "0": 0.076, "1": 0.844, "2": 0.067, "3": 0.013 },
                    "confidence": 0.585 },
    "area":       { "type": "choice", "choice": "ui",
                    "probabilities": { "payments": 0.006, "ui": 0.988, "infra": 0.006 },
                    "confidence": 0.933 }
  },
  "usage": { "input_tokens": 376, "output_tokens": 0 }
}
```

- `output_tokens: 0` — 文章を生成せず決定のみを返すのが clef の本質
- リクエスト形式: `state`(文字列 / オブジェクト / 配列)+ `questions`(id → `{type, instructions, criteria}`)

### Workers AI(Cloudflare ホスティング)

```typescript
const result = await env.AI.run("@cf/cloudflare/clef", {
  state: "...",
  questions: { ok: { type: "noul", instructions: "..." } },
});
```

---

## 2. 実用的事例(GitHub で確認した実装)

### 2.1 本番品質ゲート:エージェント出力の自動承認 / エスカレーション
**[nicia-ai/admission-decision-eval](https://github.com/nicia-ai/admission-decision-eval)**

- AI エージェントが共有ナレッジベースに書き込む内容の**「自動承認 / 人間レビュー」判定**を判断モデルで行えるかの検証(ラベル付き85件)
- 結果:
  - **Jev と Kev-27B が全件正解**。clef-flash(9B)等は「このタスクでは出たままでは使えない」
  - **clef は決定論的**(同一入力で同一回答)だが、**レコード順序に回答が依存**する特性
  - レイテンシ:Jev ~100–170ms / clef ~650–700ms。3パス運用でも**$0.25未満**
- 社内検証の雛形としてそのまま再利用できる構成

### 2.2 ピクセルから直接操作するゲーム AI
**[edumntg/jev-clef-experiments](https://github.com/edumntg/jev-clef-experiments)**

- スーパーマリオブラザーズ1-1を**ピクセル画像のみで攻略**。直前4フレームを clef に送り、確率→アクションへマッピング
- **68回の判断呼び出しで1-1をクリア**
- 反面、振り子系の物理シミュレーション制御では**どのモデルも2秒以上の安定保持に失敗** — 「clef はピクセルのみだと逆方向に押す」という失敗記録も含む
- 判断モデルの**実用範囲の境界(マルチモーダル認識は強い / 精密制御は苦手)**を知るよい検証

### 2.3 地理知識の圧力テスト「Blind-Earth」
**[dylanler/blind-earth-clef-jev](https://github.com/dylanler/blind-earth-clef-jev)** / [move38studios/decision-map-bench](https://github.com/move38studios/decision-map-bench)

- 緯度経度グリッド(16,200点)の各セルに「陸か海か?」の二択を投げ、**世界地図を生成**
- 結果:全モデルが**陸地を過大予測**(clef 0.383 / clef-flash 0.511 / Jev 0.487、**真値 0.29**)
- 判断モデルの世界知識の限界を定量するベンチとして機能

### 2.4 Apple Silicon でのローカル推論エンジン
**[zknpr/cleffa](https://github.com/zknpr/cleffa)**

- **C11 + Metal 4 のネイティブ推論エンジン**(M5 Max 128GB 向け)。BF16 重み、量子化なし
- 中央値レイテンシ:**clef-flash 116ms**(PyTorch MPS 199ms 対比)/**27B 389ms**(対 579ms)
- 短いリクエストでは**ホストされた Jev API よりローカルが速い**
- `./clef-server` で **`POST /v1/systemone` をローカルに公開** → データを社外に出さず Jev 互換 API を使える
- 要件:clef-flash 32GB+ RAM / 27B 64GB+ RAM

### 2.5 セルフホスト型 MCP サーバ(エージェントに判断を差し込む)
**[beremaran/jevjam](https://github.com/beremaran/jevjam)**

- **単一 GPU の Docker コンテナ**で「Jev 互換 HTTP API + MCP サーバ」を提供
- 小規模判断モデルをルーティング: **Laya**(デフォルト、テキスト/JSON)→ **Julia-1**(144M)→ **clef-flash**(9B、**画像・動画まで対応**)
- VRAM にチェックポイントを1つだけ保持し、アイドル時はスリープ
- 既存の Jev 連携コードを変更せず、MCP 経由でエージェントに判断機能を接続

### 2.6 確率較正の再現可能な検証
**[B-Deforce/jev-clef-calibration](https://github.com/B-Deforce/jev-clef-calibration)**

- 感情分析500件 + マスク済みSMS500件に同じ yes/no 質問を投げ、**Jev と clef の出力確率をラベルと照合**
- 精度 / Brier / log loss / ECE / ECCE-R + **2,000回ブートストラップによる信頼区間**
- 「較正された確率を売りにするモデル」の確率の信頼性を検証するテンプレート

### 2.7 その他(エコシステム)

| リポジトリ | 内容 |
|---|---|
| [assb-lab/clef-server](https://github.com/assb-lab/clef-server) | clef / clef-flash の推論サーバ + Python クライアント(Jev/SystemOne API) |
| [Arcobalneo/open-jevlike-infer](https://github.com/Arcobalneo/open-jevlike-infer) | オープン判断モデル向け本番推論サーバ(`/v1/systemone` 互換) |
| [rmax-ai/jev-vs-clef](https://github.com/rmax-ai/jev-vs-clef) | Jev vs Cloudflare clef のヘッドツウヘッド比較 |
| [dylanler/blind-earth-clef-jev](https://github.com/dylanler/blind-earth-clef-jev) | 地図生成ベンチ(上記参照) |

---

## 3. Claude Code からの利用(MCP として)

### 3.1 セットアップ(検証済み構成)

サーバ本体はリポジトリの `clef_mcp.py`(Python + `mcp` SDK v1、FastMCP):

```bash
git clone https://github.com/kanedayo/clef-mcp.git
cd clef-mcp
./install.sh    # venv 作成 + 依存インストール

# Claude Code への登録(ユーザースコープ)
CLEF_BASE_URL=http://<ollamaホスト>:11434 ./install.sh --register
# (または手動で:
# claude mcp add clef -s user -e CLEF_BASE_URL=http://<ollamaホスト>:11434 \
#   -- "$(pwd)/.venv/bin/python" "$(pwd)/clef_mcp.py")

# 確認
claude mcp list    # clef: ... - ✔ Connected
```

> `mcp` SDK は **v1 を固定**(`requirements.txt` で `mcp<2`)。2.x では FastMCP が MCPServer に改名されています。

提供ツール:

- `mcp__clef__decide(state, questions)` — System One 形式で判断を依頼
- `mcp__clef__health()` — Ollama 到達性・バージョン・設定の確認

設定は環境変数で制御:`CLEF_BASE_URL`(デフォルトは `OLLAMA_HOST`、なければ `http://localhost:11434`)/ `CLEF_MODEL`(デフォルト `clef`)/ `CLEF_TIMEOUT`(デフォルト 180秒)。

> **注意(本環境でのハマりポイント)**:環境変数 `OLLAMA_HOST` が設定されている場合、`ollama` CLI はそのリモートインスタンスを参照します。モデルのある側(`ollama list` で確認)と `CLEF_BASE_URL` を一致させましょう。

### 3.2 使い方

セッション再起動でツールが読み込まれます。自然言語で指示するだけ:

> 「このPRの差分を clef でレビューして、マージ可否・リスクレベル・影響範囲を判定して」

Claude Code が差分を `state` に整形して `mcp__clef__decide` を呼び、確率付きの結果を解釈して報告します。

**役割分担の原則**: 生成と推論は Claude に残し、**「高頻度・二択〜数択・高速でいい」判断**(分類・トリアージ・マージリスク・意図検出・出力チェック)だけ clef に分流する。

---

## 4. 実装上の指針(事例から読み取れること)

1. **高品質な品質ゲート**(承認/エスカレーション)には 27B 級が有効。9B はタスク次第では不十分(2.1 の検証結果)
2. **マルチモーダル(画像/動画)が必要なら clef 系が Jev より強い**(Jev はテキストのみ)
3. **レイテンシ重視なら clef-flash**(中央値 ~39ms 級)やローカル推論(cleffa)
4. **決定論だが順序依存の可能性がある** — バッチ処理ではレコード順序の影響を確認する(2.1)
5. **精密制御には不向き** — 認識・分類は強いが、連続量・フィードバック制御は期待しない(2.2)
6. **API 互換が最大の価値** — Jev 連携をそのまま clef に差し替えて、マルチモーダル・セルフホスト性・低コストを得られる
7. ベンチ・料金は**各社の自己報告が中心**。採用判断前に 2.1 / 2.6 型の自社データ検証を

---

## 参考

- Cloudflare Workers AI: [clef](https://developers.cloudflare.com/workers-ai/models/clef/) / [clef-flash](https://developers.cloudflare.com/workers-ai/models/clef-flash/)
- Hugging Face: [Cloudflare/clef](https://huggingface.co/Cloudflare/clef) / [Cloudflare/clef-flash](https://huggingface.co/Cloudflare/clef-flash)
- Ollama: [clef](https://ollama.com/library/clef)
- Jev / System One API 仕様(互換の参照): [docs.typesafe.ai](https://docs.typesafe.ai/introduction)
- 日本語の Jev 解説(Zenn): [高速判断AI Jevのユースケースとオープン実装](https://zenn.dev/karage0703/articles/jev-use-cases-open-implementations)
