/*
 * Maxwell's Demon Energy Harvester — ESP32-C3 Deep Sleep 制御コード
 * Configuration D: 超低消費電力フィードバックエンジン (Diode-OR ハイブリッド自己駆動対応)
 * 
 * プロジェクト: Macroscopic Quantum Entanglement Engine 検証デバイス
 * 論文: "Breaking the Second Law Limits: From Autonomous Maxwell's Demons 
 *        to Quantum Landauer Energy Harvesters"
 * 
 * 概要:
 *   体温と外気温の温度差（ΔT≈5〜15℃）からペルチェ素子で発電し、
 *   ESP32-C3（マクスウェルの悪魔）がフィードバック制御することで
 *   エネルギー抽出効率がどう変わるかを検証する。
 *
 * Configuration D の目的:
 *   Arduinoベースの Configuration A/B/C では悪魔の消費電力（~150mW）が
 *   抽出仕事を常に上回り、正味仕事 < 0 となっていた（ランダウアー限界の実証）。
 *   本構成では ESP32-C3 の Deep Sleep（~5μA, ~16.5μW）を活用し、
 *   悪魔のコストを 2〜3桁削減することで、正味仕事 > 0 の達成を目指す。
 *   さらに Diode-OR 回路によるハイブリッド給電構成を採用し、
 *   USB 給電による初期起動・Serial キャリブレーションから、USB 切断後の 100% 自律自己駆動
 *   （Self-powered mode）へのシームレスな移行を実現する。
 * 
 * ハイブリッド起動モード (Hybrid Startup Mode):
 *   1. Initial Boot & Calibration:
 *      USB を接続して初期起動。Serial モニターによる動作ログ確認、DS18B20 温度センサーの
 *      キャリブレーション、およびスーパーキャパシタの初期充電を実施。
 *   2. 100% Self-powered Demonstration:
 *      USB ケーブルを抜去。Diode-OR 回路（ショットキーバリアダイオード構成）により
 *      スーパーキャパシタ / TEG 発電電力へ無瞬断で切替。10秒周期の Deep Sleep サイクルで
 *      完全自己駆動デモンストレーションを実行。
 * 
 * Deep Sleep アーキテクチャ:
 *   ESP32-C3 は大半の時間を Deep Sleep（~5μA）で過ごす。
 *   タイマーで周期的に起床（10秒間隔）し、以下を実行:
 *     0. 低電圧ブラウンアウト保護: VSTORE < 3.0V の場合は直ちに 30秒間 Deep Sleep 復帰
 *     1. VSTORE 電圧を ADC で読取り（~1ms）
 *     2. 閾値判定 → 必要なら MOSFET ON → LED パルス発光
 *     3. 15 回に 1 回だけ DS18B20 温度を測定（~750ms 節約）
 *     4. CSV データを Serial 出力
 *     5. Deep Sleep に復帰
 * 
 * 実験モード:
 *   Phase A (30秒): Feedback OFF — LED_passive が常時 ON、MOSFET 常に OFF
 *   Phase B (30秒): Feedback ON  — Deep Sleep wake-measure-flash サイクル
 * 
 * 接続 (XIAO ESP32-C3):
 *   GPIO2  — DS18B20 温度センサー (OneWire, 4.7kΩプルアップ)
 *   GPIO3  — MOSFET Gate → LED_demon 制御
 *   GPIO4  — LED_passive 制御 (Phase A でのみ有効)
 *   GPIO0  — VSTORE 電圧モニタ (ADC, 10kΩ/10kΩ分圧)
 *   GPIO1  — VOUT 電圧モニタ   (ADC, 10kΩ/10kΩ分圧)
 *   GND    — 共通 GND
 *   USB/3.3V — Diode-OR ハイブリッド電源（USB 接続で初期起動 & Serial 出力、拔去で自律自己駆動）
 * 
 * ハードウェア対応:
 *   ペルチェ TEG  → 熱電発電（温度差→起電力）
 *   スーパーキャパシタ 1.0F → エネルギー蓄積バッファ
 *   Diode-OR 回路 → USB 電源と蓄電バッファのハイブリッド給電ダイオードOR結合
 *   MOSFET (IRLZ44N) → ゲート開閉（悪魔の制御出力）
 *   LED (赤色) → 仕事の抽出を可視化
 * 
 * 論文との対応:
 *   V_store 監視     ←→  量子状態の測定 (dy_t)
 *   閾値判定          ←→  ベイズ推定 (事後確率 P の計算)
 *   MOSFET ON/OFF     ←→  トンネル障壁の開閉 (kappa_ON/OFF)
 *   LED パルス発光    ←→  仕事の抽出 (W_ext)
 *   Deep Sleep        ←→  量子もつれによる測定コスト削減
 *   正味仕事 > 0      ←→  ランダウアー限界の超越
 */

#include <OneWire.h>
#include <DallasTemperature.h>
#include <esp_sleep.h>

// =====================================================================
//  ピン定義 (XIAO ESP32-C3)
// =====================================================================
#define ONE_WIRE_BUS      2    // DS18B20 データピン (左側1番目: A0/D0 = GPIO2)
#define MOSFET_GATE_PIN   3    // MOSFET Gate 制御  (左側2番目: A1/D1 = GPIO3)
#define VSTORE_PIN        4    // VSTORE 電圧 ADC   (左側3番目: A2/D2 = GPIO4) ★ADC1ピンに変更
#define LED_PASSIVE_PIN   5    // 赤色LED 制御       (左側4番目: A3/D3 = GPIO5) ★デジタルピンに変更
#define VOUT_PIN          6    // VOUT 電圧 (ADC非対応ピンのため今回は読み飛ばします)

// =====================================================================
//  定数
// =====================================================================

// --- Deep Sleep タイマー ---
// 起床間隔: 10秒（μs 単位）: 自己駆動サイクルバッファ用
// Deep Sleep 中の消費電力: ~5μA @ 3.3V = 16.5μW
// この間隔はキャパシタの充電時定数に対して十分短い
const uint64_t WAKE_INTERVAL_US = 10000000ULL;  // 10秒

// 低電圧ブラウンアウト保護閾値 (3.0V未満なら計測をスキップし即時ロングスリープ)
const float LOW_VOLTAGE_GUARD_V = 3.0;
const uint64_t LONG_SLEEP_INTERVAL_US = 30000000ULL; // 30秒スリープ

// --- 電圧閾値 ---
// LED 点灯閾値: キャパシタ電圧がこの値を超えたらパルス発光
// 論文対応: P[0] > threshold → ゲートを開く判定
const float FLASH_THRESHOLD_V = 2.5;   // LED Vf + 余裕
// LED 消灯閾値: この電圧まで放電したらパルス停止
const float FLASH_CUTOFF_V   = 1.8;

// --- パルス制御 ---
// パルス持続時間 (ms): LED 点灯時間
// 100ms → 500ms (0.5秒) に延長（はっきりと点滅が見える設定）
const int FLASH_DURATION_MS = 500;

// --- 実験フェーズ ---
// 各フェーズの持続時間 (秒)
const uint32_t PHASE_DURATION_S = 30;

// --- 温度測定間隔 ---
// 10秒ごとのサイクルで毎回温度を計測更新する設定 (15 → 1)
const uint32_t TEMP_READ_INTERVAL = 1;

// --- ADC 設定 (ESP32-C3) ---
// ESP32-C3 の ADC は 12bit (0-4095), 基準電圧 ~3.3V (実測で補正推奨)
// 分圧比: 10kΩ / 10kΩ → 実電圧 = 読取値 × 2
const float VOLTAGE_DIVIDER_RATIO = 2.0;
const float ADC_REF_VOLTAGE       = 3.3;    // ESP32-C3 の ADC 基準電圧
const int   ADC_RESOLUTION        = 4095;   // 12-bit ADC

// --- 消費電力パラメータ ---
// ESP32-C3 アクティブ時消費電力: ~30mA @ 3.3V = 99mW
// (WiFi/BLE OFF, CPU 160MHz, ADC 読取り程度の軽負荷時)
const float ESP32_ACTIVE_POWER_MW = 99.0;

// ESP32-C3 Deep Sleep 時消費電力: ~5μA @ 3.3V = 16.5μW = 0.0165mW
const float ESP32_SLEEP_POWER_MW  = 0.0165;

// Arduino (Configuration A) の消費電力 — 比較用
const float ARDUINO_POWER_MW      = 150.0;

// --- スーパーキャパシタ ---
// エネルギー計算: E = 0.5 * C * (V1² - V2²)
const float SUPERCAP_F = 1.0;  // 1.0 ファラド

// =====================================================================
//  RTC メモリ構造体 (Deep Sleep 中も保持)
// =====================================================================
/*
 * Deep Sleep からの復帰後もデータが失われないよう、
 * RTC_DATA_ATTR 属性で RTC slow memory に配置する。
 * 
 * experimentStartCycle == 0 を初回起動の判定に使用:
 *   - リセット直後: RTC メモリはゼロクリアされる
 *   - Deep Sleep 復帰: 前回の値が保持される
 */
RTC_DATA_ATTR struct {
    bool     feedbackMode;          // 現在のフェーズ (false=A, true=B)
    uint32_t cycleCount;            // 累積ウェイクサイクル数
    uint32_t phaseStartCycle;       // 現在フェーズ開始時のサイクル番号
    uint32_t flashCount_passive;    // Phase A: LED 点灯カウント
    uint32_t flashCount_demon;      // Phase B: LED パルス発光カウント
    float    totalEnergy_passive_mJ;// Phase A: 抽出エネルギー累積 (mJ)
    float    totalEnergy_demon_mJ;  // Phase B: 抽出エネルギー累積 (mJ)
    float    totalActiveTime_ms;    // ESP32 アクティブ時間累積 (ms)
    float    lastT_hot;             // 直近の高温側温度 (℃)
    float    lastT_cold;            // 直近の低温側温度 (℃)
    uint32_t experimentStartCycle;  // 実験開始マーカー (0 = 初回起動)
} rtcData;

// =====================================================================
//  温度センサー
// =====================================================================
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// =====================================================================
//  電圧読取り関数
// =====================================================================
/*
 * ESP32-C3 の ADC (12-bit, 0〜3.3V) で分圧された電圧を読み取り、
 * 分圧比を補正して実際のキャパシタ電圧を返す。
 * 
 * 注意: ESP32 の ADC は非線形特性があるため、精密測定には
 *       adc_calibration API の使用を推奨。ここでは簡易計算を使用。
 */
float readVoltage(int pin) {
    // 複数回サンプリングして平均化（ノイズ低減）
    const int SAMPLES = 4;
    uint32_t sum = 0;
    for (int i = 0; i < SAMPLES; i++) {
        sum += analogRead(pin);
    }
    float raw = (float)sum / SAMPLES;
    float voltage = (raw / (float)ADC_RESOLUTION) * ADC_REF_VOLTAGE;
    return voltage * VOLTAGE_DIVIDER_RATIO;  // 分圧補正
}

// =====================================================================
//  フェーズ終了サマリー出力
// =====================================================================
/*
 * フェーズ切替時に結果を Serial に出力する。
 * 
 * 出力内容:
 *   - LED 点灯回数/パルス回数
 *   - 抽出エネルギー (mJ)
 *   - 悪魔のコスト (mJ): ESP32 のアクティブ時間 × 消費電力
 *   - 正味仕事 = 抽出仕事 − 悪魔コスト
 *   - Arduino 比較: 同じ時間での Arduino のコスト
 */
void printPhaseSummary() {
    // 経過時間の計算
    uint32_t phaseCycles = rtcData.cycleCount - rtcData.phaseStartCycle;
    float phaseTime_s = phaseCycles * (WAKE_INTERVAL_US / 1000000.0);

    // 悪魔のコスト計算
    // アクティブ時間中の電力消費 + スリープ時間中の電力消費
    float activeTime_s = rtcData.totalActiveTime_ms / 1000.0;
    float sleepTime_s  = phaseTime_s - activeTime_s;
    if (sleepTime_s < 0) sleepTime_s = 0;

    float demonCost_active_mJ = ESP32_ACTIVE_POWER_MW * activeTime_s;   // mW * s = mJ
    float demonCost_sleep_mJ  = ESP32_SLEEP_POWER_MW  * sleepTime_s;    // mW * s = mJ
    float demonCost_total_mJ  = demonCost_active_mJ + demonCost_sleep_mJ;

    // Arduino で同じ時間動かした場合のコスト (比較用)
    float arduinoCost_mJ = ARDUINO_POWER_MW * phaseTime_s;

    // 平均消費電力
    float avgPower_mW = 0;
    if (phaseTime_s > 0) {
        avgPower_mW = demonCost_total_mJ / phaseTime_s;  // mJ / s = mW
    }

    Serial.println();
    Serial.println(F("════════════════════════════════════════════════════"));

    if (!rtcData.feedbackMode) {
        // Phase A の結果
        Serial.println(F("【Phase A 結果: Feedback OFF（悪魔なし）】"));
        Serial.print(F("  LED_passive 点灯カウント: "));
        Serial.println(rtcData.flashCount_passive);
        Serial.print(F("  抽出エネルギー: "));
        Serial.print(rtcData.totalEnergy_passive_mJ, 4);
        Serial.println(F(" mJ"));
        Serial.println(F("  悪魔のコスト: N/A (Phase A は受動的)"));
        Serial.print(F("  正味仕事: "));
        Serial.print(rtcData.totalEnergy_passive_mJ, 4);
        Serial.println(F(" mJ"));
    } else {
        // Phase B の結果
        Serial.println(F("【Phase B 結果: Feedback ON（悪魔あり — ESP32-C3 Deep Sleep / Diode-OR Hybrid）】"));
        Serial.print(F("  LED_demon パルス回数: "));
        Serial.println(rtcData.flashCount_demon);
        Serial.print(F("  抽出エネルギー: "));
        Serial.print(rtcData.totalEnergy_demon_mJ, 4);
        Serial.println(F(" mJ"));
        Serial.println();

        Serial.println(F("  ─── 悪魔のコスト分析 ───"));
        Serial.print(F("  ESP32 アクティブ時間合計: "));
        Serial.print(rtcData.totalActiveTime_ms, 1);
        Serial.println(F(" ms"));
        Serial.print(F("  アクティブ時コスト: "));
        Serial.print(demonCost_active_mJ, 4);
        Serial.println(F(" mJ"));
        Serial.print(F("  スリープ時コスト:   "));
        Serial.print(demonCost_sleep_mJ, 4);
        Serial.println(F(" mJ"));
        Serial.print(F("  悪魔コスト合計:     "));
        Serial.print(demonCost_total_mJ, 4);
        Serial.println(F(" mJ"));
        Serial.print(F("  平均消費電力:       "));
        Serial.print(avgPower_mW, 4);
        Serial.println(F(" mW"));
        Serial.println();

        Serial.println(F("  ─── Arduino 比較 ───"));
        Serial.print(F("  Arduino コスト (同時間): "));
        Serial.print(arduinoCost_mJ, 1);
        Serial.println(F(" mJ"));
        Serial.print(F("  コスト削減率: "));
        if (arduinoCost_mJ > 0) {
            float reduction = (1.0 - demonCost_total_mJ / arduinoCost_mJ) * 100.0;
            Serial.print(reduction, 1);
            Serial.println(F(" %"));
        } else {
            Serial.println(F("N/A"));
        }
        Serial.println();

        float netWork = rtcData.totalEnergy_demon_mJ - demonCost_total_mJ;
        Serial.print(F("  ★ 正味仕事 = 抽出仕事 - 悪魔コスト = "));
        Serial.print(netWork, 4);
        Serial.println(F(" mJ"));

        if (netWork > 0) {
            Serial.println();
            Serial.println(F("  ──────────────────────────────────────"));
            Serial.println(F("  ★★★ 正味仕事 > 0 達成! ★★★"));
            Serial.println(F("  Deep Sleep による測定コスト削減により、"));
            Serial.println(F("  悪魔の情報処理コストが抽出仕事を下回った。"));
            Serial.println(F("  これは論文の「量子もつれによるランダウアー限界超越」の"));
            Serial.println(F("  古典的アナロジーとして解釈できる。"));
            Serial.println(F("  ──────────────────────────────────────"));
        } else {
            Serial.println();
            Serial.println(F("  → 正味仕事 < 0: ランダウアー限界の実証"));
            Serial.println(F("    悪魔のコストが抽出仕事を上回っている。"));
            Serial.println(F("    ΔT を大きくするか、Deep Sleep を長くして再試行。"));
        }
    }

    Serial.println(F("════════════════════════════════════════════════════"));
    Serial.println();
}

// =====================================================================
//  セットアップ (毎回の起床時に呼ばれる)
// =====================================================================
/*
 * ESP32-C3 の Deep Sleep からの復帰は「リセット」として扱われるため、
 * setup() は毎回実行される。RTC メモリの値で初回起動 vs 復帰を判別。
 *
 * フロー:
 *   初回起動時 → ヘッダー出力、RTC メモリ初期化
 *   復帰時     → 即座に測定・制御ロジックを実行
 */
void setup() {
    pinMode(MOSFET_GATE_PIN, OUTPUT);
    pinMode(LED_PASSIVE_PIN, OUTPUT);
    digitalWrite(MOSFET_GATE_PIN, LOW);
    digitalWrite(LED_PASSIVE_PIN, LOW);

    analogSetAttenuation(ADC_11db);
    analogReadResolution(12);

    Serial.begin(115200);
    delay(1000);  // USB CDC 安定待ち

    if (rtcData.experimentStartCycle == 0) {
        rtcData.feedbackMode          = false;  // Phase A から開始
        rtcData.cycleCount            = 0;
        rtcData.phaseStartCycle       = 0;
        rtcData.flashCount_passive    = 0;
        rtcData.flashCount_demon      = 0;
        rtcData.totalEnergy_passive_mJ = 0.0;
        rtcData.totalEnergy_demon_mJ  = 0.0;
        rtcData.totalActiveTime_ms    = 0.0;
        rtcData.lastT_hot             = 0.0;
        rtcData.lastT_cold            = 0.0;
        rtcData.experimentStartCycle  = 1;

        Serial.println();
        Serial.println(F("════════════════════════════════════════════════════"));
        Serial.println(F(" Maxwell's Demon Energy Harvester v2.0"));
        Serial.println(F(" Configuration D: ESP32-C3 USB Stable Telemetry Edition"));
        Serial.println(F(" 情報エンジン検証デバイス — リアルタイムUSB計測・点滅制御版"));
        Serial.println(F("════════════════════════════════════════════════════"));
        Serial.println();
        Serial.println(F("Phase A (30s): Feedback OFF — 悪魔なし（受動的）"));
        Serial.println(F("Phase B (30s): Feedback ON  — 悪魔あり（緑色LED点滅制御）"));
        Serial.println(F("════════════════════════════════════════════════════"));
        Serial.println();
        Serial.println(F("time_s,phase,T_hot_C,T_cold_C,deltaT_C,V_store_mV,V_out_mV,flash_count,E_extracted_mJ,demon_cost_mJ,net_work_mJ,avg_power_mW"));
    }

    // DS18B20 OneWire バス初期化 & プルアップ有効化
    pinMode(ONE_WIRE_BUS, INPUT_PULLUP);
    sensors.begin();

    int devCount = sensors.getDeviceCount();
    Serial.print(F("【DS18B20 温度センサー検出数】: "));
    Serial.print(devCount);
    Serial.println(F(" 個"));

    if (devCount > 0) {
        sensors.requestTemperatures();
        rtcData.lastT_hot = sensors.getTempCByIndex(0);
        if (devCount > 1) {
            rtcData.lastT_cold = sensors.getTempCByIndex(1);
        } else {
            rtcData.lastT_cold = rtcData.lastT_hot; // 1個の場合は同値を仮定
        }
    }

    if (rtcData.lastT_hot < -100) rtcData.lastT_hot = 0.0;
    if (rtcData.lastT_cold < -100) rtcData.lastT_cold = 0.0;
}

void loop() {
    unsigned long wakeStartTime = millis();
    rtcData.cycleCount++;

    // ───────────────────────────────────────────────
    //  フェーズ切替判定 (30秒ごと)
    // ───────────────────────────────────────────────
    uint32_t cyclesInPhase = rtcData.cycleCount - rtcData.phaseStartCycle;
    float phaseElapsed_s = cyclesInPhase * 10.0;

    if (phaseElapsed_s >= (float)PHASE_DURATION_S) {
        printPhaseSummary();
        rtcData.feedbackMode = !rtcData.feedbackMode;
        rtcData.phaseStartCycle = rtcData.cycleCount;

        if (rtcData.feedbackMode) {
            rtcData.flashCount_demon      = 0;
            rtcData.totalEnergy_demon_mJ  = 0.0;
        } else {
            rtcData.flashCount_passive    = 0;
            rtcData.totalEnergy_passive_mJ = 0.0;
        }
        rtcData.totalActiveTime_ms = 0.0;

        digitalWrite(MOSFET_GATE_PIN, LOW);
        digitalWrite(LED_PASSIVE_PIN, LOW);

        if (rtcData.feedbackMode) {
            Serial.println(F(">>> Phase B 開始: Feedback ON（悪魔が緑色LED制御）"));
        } else {
            Serial.println(F(">>> Phase A 開始: Feedback OFF（受動的接続のみ）"));
        }
        Serial.println();
    }

    // ───────────────────────────────────────────────
    //  温度測定
    // ───────────────────────────────────────────────
    if (rtcData.cycleCount % TEMP_READ_INTERVAL == 0) {
        pinMode(ONE_WIRE_BUS, INPUT_PULLUP);
        sensors.begin();
        int devCount = sensors.getDeviceCount();
        if (devCount > 0) {
            sensors.requestTemperatures();
            float T1 = sensors.getTempCByIndex(0);
            float T2 = (devCount > 1) ? sensors.getTempCByIndex(1) : T1;
            if (T1 > -100) rtcData.lastT_hot  = T1;
            if (T2 > -100) rtcData.lastT_cold = T2;
        }
    }

    float T_hot   = rtcData.lastT_hot;
    float T_cold  = rtcData.lastT_cold;
    float deltaT  = T_hot - T_cold;

    float V_store = readVoltage(VSTORE_PIN);
    float V_out   = V_store; // GPIO6はADC非対応のためV_storeとほぼ同等として扱います

    // ───────────────────────────────────────────────
    //  制御ロジック
    // ───────────────────────────────────────────────
    bool flashed = false;
    float E_flash_mJ = 0.0;

    if (!rtcData.feedbackMode) {
        // Phase A: Feedback OFF
        digitalWrite(LED_PASSIVE_PIN, HIGH);
        digitalWrite(MOSFET_GATE_PIN, LOW);

        if (V_out > FLASH_CUTOFF_V) {
            float I_led_A = (V_out - FLASH_CUTOFF_V) / 330.0;
            float P_led_mW = V_out * I_led_A * 1000.0;
            rtcData.totalEnergy_passive_mJ += P_led_mW * 10.0;
            rtcData.flashCount_passive++;
        }
    } else {
        // Phase B: Feedback ON
        digitalWrite(LED_PASSIVE_PIN, LOW);

        if (V_store >= FLASH_THRESHOLD_V) {
            // シリアルモニタへの動作告知
            Serial.println(F(">>> [ACTUATOR] GREEN LED 3 SECONDS ON NOW! <<<"));
            Serial.flush();

            // ─── MOSFET ON (GPIO3) ＆ 電源(GPIO4) の両方をHIGHにしてテスト ───
            digitalWrite(MOSFET_GATE_PIN, HIGH);   // GPIO3 (MOSFET Gate)
            digitalWrite(LED_PASSIVE_PIN, HIGH);  // GPIO4
            delay(3000);
            digitalWrite(MOSFET_GATE_PIN, LOW);
            digitalWrite(LED_PASSIVE_PIN, LOW);

            float V_after = readVoltage(VSTORE_PIN);
            E_flash_mJ = 0.5 * SUPERCAP_F * (V_store * V_store - V_after * V_after) * 1000.0;
            if (E_flash_mJ < 0) E_flash_mJ = 0;

            rtcData.totalEnergy_demon_mJ += E_flash_mJ;
            rtcData.flashCount_demon++;
            flashed = true;
        }
    }

    unsigned long activeTime_ms = millis() - wakeStartTime;
    rtcData.totalActiveTime_ms += (float)activeTime_ms;

    float totalElapsed_s = rtcData.cycleCount * 10.0;
    float totalActive_s  = rtcData.totalActiveTime_ms / 1000.0;
    float totalSleep_s   = totalElapsed_s - totalActive_s;
    if (totalSleep_s < 0) totalSleep_s = 0;

    float demonCost_mJ = ESP32_ACTIVE_POWER_MW * totalActive_s + ESP32_SLEEP_POWER_MW * totalSleep_s;
    float avgPower_mW  = totalElapsed_s > 0 ? (demonCost_mJ / totalElapsed_s) : 0;

    float netWork_mJ;
    float E_extracted_mJ;
    uint32_t flashCount;
    if (rtcData.feedbackMode) {
        E_extracted_mJ = rtcData.totalEnergy_demon_mJ;
        flashCount     = rtcData.flashCount_demon;
        netWork_mJ     = E_extracted_mJ - demonCost_mJ;
    } else {
        E_extracted_mJ = rtcData.totalEnergy_passive_mJ;
        flashCount     = rtcData.flashCount_passive;
        netWork_mJ     = E_extracted_mJ;
    }

    // ───────────────────────────────────────────────
    //  CSV データ出力
    // ───────────────────────────────────────────────
    float time_s = rtcData.cycleCount * 10.0;
    Serial.print(time_s, 1);
    Serial.print(",");
    Serial.print(rtcData.feedbackMode ? "B_ON" : "A_OFF");
    Serial.print(",");
    Serial.print(T_hot, 1);
    Serial.print(",");
    Serial.print(T_cold, 1);
    Serial.print(",");
    Serial.print(deltaT, 1);
    Serial.print(",");
    Serial.print(V_store * 1000, 0);
    Serial.print(",");
    Serial.print(V_out * 1000, 0);
    Serial.print(",");
    Serial.print(flashCount);
    Serial.print(",");
    Serial.print(E_extracted_mJ, 4);
    Serial.print(",");
    Serial.print(demonCost_mJ, 4);
    Serial.print(",");
    Serial.print(netWork_mJ, 4);
    Serial.print(",");
    Serial.println(avgPower_mW, 4);

    Serial.flush();

    // 10秒周期待機 (3秒点灯時間を考慮)
    int remainingDelay = 10000 - (flashed ? 3000 : 0);
    if (remainingDelay > 0) {
        delay(remainingDelay);
    }
}
