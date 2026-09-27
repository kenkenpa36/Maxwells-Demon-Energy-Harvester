# TDD 証跡 — ESP32-C3 ファームウェア 発電効率改善 (v2)

**対象**: `thermal_demo_design/maxwell_demon_harvester_esp32c3_v2.ino`（新規。旧版 `maxwell_demon_harvester_esp32c3.ino` は無変更で残置）/ `demon_policy.h`
**ブランチ**: `tdd/esp32c3-harvest-efficiency`
**作成日**: 2026-09-27
**元プラン**: `*.plan.md` は無し。ユーザー指示「更に発電効率を上げれるように修正してください」から本セッションでジャーニーを導出。

---

## 1. 背景: 何が非効率だったか

旧ファームウェアは Deep Sleep からの **毎起床時に無条件で `delay(3000)`** を実行していた（USB シリアルモニタを開く猶予）。
ESP32-C3 の起床中消費を 20 mA × 3.3 V ≈ 66 mW と見積もると、これは **1 起床あたり約 200 mJ** の浪費で、
ファームウェアが「悪魔のコスト」として計上していた Deep Sleep 電力（0.0165 mW × 25 s ≈ 0.4 mJ）の **約 500 倍** に相当する。
体温 ΔT≈10℃ の TEG 出力（数 mW）では 25 秒スリープで貯まるのは数十〜百数十 mJ なので、この待機だけで収支が赤字になっていた。

## 2. ユーザージャーニー

| # | ジャーニー | 対応関数 |
|---|---|---|
| J1 | 体温でプレートを温めたユーザーとして、電圧と温度差が条件を満たした時だけ SOS を光らせたい | `decideDemon` |
| J2 | 自律運転するデバイスとして、キャパシタが発光可能になるタイミングまで無駄に起きずに眠りたい | `selectSleepUs`, `predictChargeSleepUs` |
| J3 | USB を抜いて自律運転する時、起動時の USB 待機で電力を捨てたくない。USB でログ採取する時はログを落としたくない | `startupWaitBudgetMs` |
| J4 | 起床時間を短くするため、温度センサの変換中に他の作業をしたい | `remainingConversionWaitMs` |
| J5 | 実験者として、抽出仕事・スリープコスト・起床中コストを正しく記録して正味仕事を評価したい | `extractedEnergy_mJ`, `sleepCost_mJ`, `activeCost_mJ` |
| J6 | 微小温度差時にエコモードで LED 点灯エネルギーを 40% 節約したい | `morseTiming`, `morseOnTimeMs`, `morseTotalMs` |

## 3. タスクレポート

### Step 0: テストランナー
プロジェクトに JS/Python のテスト基盤は無い（`package.json`, `pyproject.toml`, `Makefile` 不在）。Arduino スケッチはホストで実行できないため、
判断ロジックを Arduino 非依存ヘッダ `demon_policy.h` に分離し、`test/run_tests.sh`（clang++ + 自前の最小ハーネス、外部依存なし）で検証する。
カバレッジは `llvm-profdata` / `llvm-cov`、スケッチ本体は `test/stubs/` の Arduino スタブに対する構文チェックで確認する。

### Step 3: RED
```
$ ./test/run_tests.sh
== build
thermal_demo_design/test/test_demon_policy.cpp:14:10: fatal error: '../demon_policy.h' file not found
1 error generated.
```
テストが参照するポリシーモジュールが存在しないことによるコンパイル時 RED（意図した失敗）。
チェックポイント: `86c6cf5 test: add host-side reproducer for ESP32-C3 demon policy (RED)`

### Step 4–5: 実装と GREEN (1 回目)
```
$ ./test/run_tests.sh --coverage --syntax
50 checks, 0 failures
Regions 62/62 (100.00%)  Functions 13/13 (100.00%)  Lines 63/63 (100.00%)  Branches 34/34 (100.00%)
== syntax check: maxwell_demon_harvester_esp32c3.ino (Arduino stubs)
   ok
```
チェックポイント: `426b670 fix: cut ESP32-C3 wake-time energy waste and add tested demon policy (GREEN)`
その後、ユーザー指示により修正版を `maxwell_demon_harvester_esp32c3_v2.ino` に改名し、旧版は無変更で復元
（`1b305b0 refactor: keep original sketch untouched, ship v2 as ...`）。

### Step 6: レビュー（code-reviewer サブエージェント + Astra クロスプロバイダレビュー）と 2 周目 RED/GREEN

Astra (gpt-6-astra) 1 回目: **FAIL** (HIGH 3)。内部 code-reviewer: WARNING (HIGH 1, MEDIUM 2, LOW 3)。確認した上で対応した指摘:

| 指摘 | 判定 | 対応 |
|---|---|---|
| `usb_serial_jtag_is_connected()` は IDF 4.4 (core 2.x) に無く、3.x でも SOF 検出のみで CDC 準備完了を意味しない | 妥当 | IDF ≥5 では SOF 検出をバス活性判定に使い、CDC 準備完了は両コア共通の `Serial` の bool 判定で早期脱出。IDF 4.4 は `Serial` のみ。`run_tests.sh --syntax` が両経路を検査 |
| 起床コストがログ送信・flush 時間を含まない | 妥当 | 起床時間の確定をログ送信・flush・drain 後に移動。CSV の `W_active_mJ`/`awake_ms` は前サイクルまでの確定値と明記 |
| センサ読取失敗時に RTC の古い ΔT で発光し続ける（v1 継承） | 妥当 | `decideDemon` に `temperatureValid` を追加し無効時は不作動。状態 `SENSOR_ERR` をログ。テスト追加 |
| ブラウンアウト等の非 Deep Sleep リセットでも 3 秒猶予に入る | 妥当 (MEDIUM) | 猶予は `esp_reset_reason()==ESP_RST_POWERON` かつ RTC 空の時のみ |
| 毎起床で `DallasTemperature::begin()`（50〜150 ms の固定遅延）とバス探索を実行 | 妥当 (MEDIUM) | ROM アドレスを RTC にキャッシュ。初回または読取失敗後のみ再探索 |
| `predictChargeSleepUs` の切り上げが float 表現誤差で 1 秒過大、巨大値の uint64 変換が UB | 妥当 (LOW) | 許容値 1 ms 付きの切り上げ、キャスト前に上限クランプ。テスト追加 |
| SOS パターンが `flashSOS` と `morseTotalMs` に二重定義 | 妥当 (LOW) | パターンをヘッダに一元化し両者が参照。テスト追加 |
| `flash_esp32c3.sh` の `SKETCH_NAME` が旧名 | 妥当 (LOW) | 既定を v2 にし環境変数で上書き可能に |

2 周目 RED（`30fc28c test: add reproducers for review findings (RED)`）:
```
$ ./test/run_tests.sh
13 errors: no matching function for call to 'decideDemon' / undeclared SOS_SYMBOL_COUNT, sosSymbolIsDash, sosGapAfterMs, sosSymbolOnMs
```
2 周目 GREEN（`14d2421 fix: address Astra + code-reviewer findings on v2 firmware (GREEN)`）:
```
$ ./test/run_tests.sh --coverage --syntax
73 checks, 0 failures
Lines 81/81 (100.00%)  Functions 16/16 (100.00%)  Branches 51/52 (98.08%)
== syntax check: maxwell_demon_harvester_esp32c3_v2.ino (Arduino stubs, IDF 4.x)  ok
== syntax check: maxwell_demon_harvester_esp32c3_v2.ino (Arduino stubs, IDF 5.x)  ok
```
（未到達だった `clampSleepUs` 上限分岐は直接テストを追加して 100% に回復。Astra 2 回目の結果は末尾に追記。）

### 実装した効率改善

| # | 変更 | 効果の見積り |
|---|---|---|
| 1 | 起動時 USB 待機を「電源投入直後の初回のみ 3 s / 前回ホスト検出時 ≤3 s 早期脱出 / 未検出時 0.3 s プローブ」に変更 | 自律運転時 1 起床あたり約 2.7 s ≈ 180 mJ 削減（最大の改善） |
| 2 | `setCpuFrequencyMhz(80)` | 起床中の消費電流を 160 MHz 比で低減 |
| 3 | DS18B20 アドレスを RTC にキャッシュし毎起床の `begin()`/探索を省略。変換 (94 ms) は USB 待機と並行 | 1 起床あたり 50〜250 ms 短縮 |
| 4 | 充電中は前回からの dV/dt で閾値到達時刻を予測して眠る（12〜60 s にクランプ） | 「起きたがまだ充電不足」の無駄な起床を排除 |
| 5 | 発光後 ΔT < 3℃ は 45 s ガードスリープ（旧: 25 s） | 微小温度差時の起床頻度を削減 |
| 6 | センサ読取失敗時は `SENSOR_ERR` で不作動 | 古い ΔT による無駄な発光を防止（v1 のバグ修正） |
| 7 | 起床中コスト `W_active_mJ`（ログ送信込み）と `W_net_total_mJ`、`awake_ms` を CSV に追加 | 悪魔の真の情報処理コストが測定できる |

## 4. テスト仕様（保証事項）

| # | 保証される振る舞い | テスト | 種別 | 結果 |
|---|---|---|---|---|
| 1 | V ≥ 2.4 V かつ ΔT ≥ 6℃ でフルパワー発光 | `acts_at_full_power_when_voltage_and_delta_t_are_high` | unit | PASS |
| 2 | 0.5 ≤ ΔT < 6℃ ではエコ発光 | `acts_in_eco_mode_when_delta_t_is_small_but_valid` | unit | PASS |
| 3 | V < 2.4 V または ΔT < 0.5℃ では発光しない | `does_not_act_when_voltage_below_flash_threshold`, `does_not_act_when_delta_t_below_minimum` | unit | PASS |
| 4 | 閾値ちょうど（2.4 V / 0.5℃ / 6.0℃）の境界挙動 | `acts_exactly_at_threshold_boundaries`, `eco_boundary_switches_to_full_power_at_eco_delta_t` | unit | PASS |
| 5 | 発光後スリープ: ΔT ≥ 8℃ → 12 s、3〜8℃ → 25 s、< 3℃ → 45 s | `after_flash_*` (3 件) | unit | PASS |
| 6 | 充電中スリープ（履歴なし）: V < 1.0 V → 60 s、それ以外 45 s | `charging_with_*` (2 件) | unit | PASS |
| 7 | 充電予測: 必要電圧 ÷ 充電速度 を秒で切り上げ | `predicts_sleep_from_charge_rate_and_rounds_up_to_seconds` | unit | PASS |
| 8 | 充電予測は 12〜60 s にクランプ、非上昇時は 60 s、履歴なしは静的ルール | `prediction_is_clamped_*` (2 件), `prediction_uses_maximum_sleep_when_voltage_is_not_rising`, `prediction_falls_back_to_static_rule_without_history` | unit | PASS |
| 9 | 電圧十分・温度差不足の時は 25 s で再確認（応答性維持） | `prediction_with_voltage_already_above_threshold_uses_eco_sleep` | unit | PASS |
| 10 | USB 待機予算: 初回 3000 ms、ホスト検出済 1500 ms、未検出 200 ms、かつ単調 | `first_boot_*`, `later_wakes_*` (3 件) | unit | PASS |
| 11 | センサ変換の残り待ち時間は経過分を差し引き、経過後は 0 | `remaining_conversion_wait_*` (2 件) | unit | PASS |
| 12 | 抽出仕事 = ½C(V₁²−V₂²)、負値は 0 にクランプ | `extracted_energy_*` (2 件) | unit | PASS |
| 13 | スリープコスト・起床コストの計算 | `sleep_cost_is_sleep_power_times_seconds`, `active_cost_is_active_power_times_awake_time`, `sleep_seconds_truncates_microseconds` | unit | PASS |
| 14 | エコモールスは点灯時間 40% 削減（900 ms vs 1500 ms）、全体 1680 ms vs 2800 ms | `eco_morse_*`, `morse_total_*`, `morse_timing_struct_matches_mode` | unit | PASS |
| 15 | 今サイクルの温度読取が無効なら、電圧・ΔT が条件を満たしても発光しない | `does_not_act_on_stale_delta_t_when_this_cycle_sensor_read_failed`, `temperature_validity_defaults_to_true_for_existing_callers` | unit | PASS |
| 16 | 充電予測は float 表現誤差で 1 秒過大にならず、極小充電速度でも UB なくクランプ。閾値ちょうどは 25 s | `prediction_tolerates_float_representation_error_in_round_up`, `prediction_with_negligible_charge_rate_does_not_overflow`, `prediction_at_exact_threshold_uses_eco_sleep`, `clamp_sleep_bounds_both_ends` | unit | PASS |
| 17 | SOS パターン（・・・ ─── ・・・、文字間は 3 ギャップ）が一元定義され、点灯・総時間はそこから導出される | `sos_pattern_*`, `sos_letter_gap_*`, `morse_totals_are_derived_from_the_sos_pattern` | unit | PASS |
| 18 | スケッチ本体が Arduino API スタブに対して IDF 4.x / 5.x 両経路で構文的に正しい | `run_tests.sh --syntax` | smoke | PASS |

## 5. カバレッジと既知のギャップ

- `demon_policy.h`: 行・関数・分岐すべて **100%**（`./test/run_tests.sh --coverage`、最終 76 チェック）。
- **未検証（ホストでは不可能）**: `.ino` 本体の実機動作。特に以下は実機で確認が必要:
  - USB ホスト検出（IDF ≥5: `usb_serial_jtag_is_connected()` による SOF 検出 + `Serial` の bool 判定、IDF 4.4: `Serial` のみ）が実機で期待通り動くこと。特に core 2.x では 0.3 s プローブ中にモニタ再接続を検出できないため、ログ採取は「電源投入直後 3 秒以内にモニタを開く」運用が前提。
  - `arduino-cli` が無いため実コアヘッダに対するコンパイルは未実施（スタブ構文チェックのみ）。
  - `setCpuFrequencyMhz(80)` 後も USB CDC ログが正常に出力されること。
  - `DallasTemperature::setWaitForConversion(false)` 経由の 9-bit 読み取りが正しい温度を返すこと。
  - RTC メモリ構造体にフィールドを追加したため、**再書き込み後の初回起動で RTC は 0 初期化される**（`experimentStartCycle == 0` で初期化パスに入る）。
- `activePower_mW = 66 mW` は推定値。実測（USB 電流計）で置き換えると `W_active_mJ` の精度が上がる。
- E2E テスト（実機でのログ採取）は本セッションでは実施していない。

## 6. マージ証跡

チェックポイントコミット（squash する場合はこの節を PR 本文にコピーする）:

- RED 1: `86c6cf5` — `./test/run_tests.sh` がコンパイル時に `'../demon_policy.h' file not found` で失敗。
- GREEN 1: `426b670` — `50 checks, 0 failures`、カバレッジ 100%、構文チェック ok。
- Refactor: `1b305b0` — v2 へ改名、旧版復元、文書更新。
- RED 2: `30fc28c` — レビュー指摘の再現テスト、13 件のコンパイルエラー。
- GREEN 2: `14d2421` — `73 checks, 0 failures`、行 100% / 分岐 98%、IDF 4.x/5.x 構文チェック ok。
- Docs / 最終: 後続コミット参照（Astra 2 回目の判定を含む）。
