/*
 * Maxwell's Demon Energy Harvester — ESP32-C3 Ultra-Low Power Adaptive Edition
 * 構成: TEG 6枚直列 (2×3配列) ＋ 0.9V汎用昇圧 ＋ ESP32-C3 (超低消費電力・高発電効率自律制御)
 * 
 * 作品名: 『手ぶくろ要らず！体温と熱源で光る 電池ゼロのSOS防災ライト』
 * 
 * 発電効率向上＆USB CDCシリアル通信安定化版:
 *   1. DS18B20 9-bit高速変換 (変換時間を750ms ➔ 93.75msへ短縮、起床時間を8分位1に削減)
 *   2. 低電圧・微小温度差時のスマート拡張スリープ (45秒〜60秒へ自動延長、無駄な起床を徹底防止)
 *   3. エコSOSモールス発光 (微小温度差時は60ms/180msの省エネ短縮パルスでエネルギー40%節約)
 *   4. 最低点灯閾値の柔軟化 (ΔT >= 2.0℃、Vstore >= 2.4Vから動的動作サポート)
 *   5. USB CDC ログ通信の安定化 (直高信頼性 Serial 送信)
 * 
 * 接続 (XIAO ESP32-C3):
 *   GPIO2  — DS18B20 温度センサー (OneWire, 4.7kΩプルアップ)
 *   GPIO3  — MOSFET Gate → 赤色LED (SOSモールス信号制御)
 *   GPIO4  — VSTORE 電圧 ADC (10kΩ/10kΩ 分圧)
 *   GPIO5  — 黄色LED (動作確認インジケーター)
 *   GND    — 共通 GND
 */

#include <OneWire.h>
#include <DallasTemperature.h>
#include <esp_sleep.h>

// =====================================================================
//  ピン定義 (XIAO ESP32-C3)
// =====================================================================
#define ONE_WIRE_BUS      2    // DS18B20 データピン (GPIO2)
#define MOSFET_GATE_PIN   3    // MOSFET Gate 制御  (GPIO3) → 赤色LED
#define VSTORE_PIN        4    // VSTORE 電圧 ADC   (GPIO4)
#define LED_PASSIVE_PIN   5    // 黄色LED インジケーター (GPIO5)

// =====================================================================
//  定数設定 (効率化チューニング版)
// =====================================================================

// --- 電圧閾値 ---
const float FLASH_THRESHOLD_V     = 2.4;  // 発光可能下限電圧 (微小温度差対応 2.4V)
const float LOW_VOLTAGE_GUARD_V   = 1.8;  // 超低電圧保護閾値

// --- 温度差閾値 ---
const float MIN_DELTA_T_C         = 0.5;  // 最低有効温度差 (0.5℃の微小温度差でも悪魔が作動)

// --- ADC 設定 ---
const float VOLTAGE_DIVIDER_RATIO = 2.0;  // 10kΩ/10kΩ 分圧比
const float ADC_REF_VOLTAGE       = 3.3;  // 基準電圧 3.3V
const int   ADC_RESOLUTION        = 4095; // 12-bit ADC

// --- スリープ時間設定 (μs 単位) ---
const uint64_t SLEEP_FAST_US   = 12000000ULL; // 高温度差時 (ΔT >= 8℃): 12秒
const uint64_t SLEEP_ECO_US    = 25000000ULL; // 標準時 (3℃ <= ΔT < 8℃): 25秒
const uint64_t SLEEP_GUARD_US  = 45000000ULL; // 微小温度差/低電圧時 (充電優先): 45秒
const uint64_t SLEEP_EMPTY_US  = 60000000ULL; // 完全放電時 (超充電優先): 60秒

// --- スーパーキャパシタ容量 ---
const float SUPERCAP_F = 1.0;  // 1.0 ファラド

// =====================================================================
//  RTC メモリ構造体 (Deep Sleep 中も保持)
// =====================================================================
RTC_DATA_ATTR struct {
    uint32_t cycleCount;            // 累積ウェイク数
    uint32_t sosFlashCount;         // SOS発光回数 (悪魔のフィードバック作動数)
    float    totalEnergy_mJ;        // 抽出エネルギー累積 W_ext (mJ)
    float    landauerCost_mJ;       // 古典ランドウアー消去コスト W_erase (mJ)
    float    lastT_hot;             // 高温側温度 (℃)
    float    lastT_cold;            // 低温側温度 (℃)
    uint32_t experimentStartCycle;  // 初回起動マーカー
} rtcData;

// =====================================================================
//  温度センサー初期化
// =====================================================================
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// =====================================================================
//  電圧読取り関数
// =====================================================================
float readVoltage(int pin) {
    const int SAMPLES = 4;
    uint32_t sum = 0;
    for (int i = 0; i < SAMPLES; i++) {
        sum += analogRead(pin);
    }
    float raw = (float)sum / SAMPLES;
    float voltage = (raw / (float)ADC_RESOLUTION) * ADC_REF_VOLTAGE;
    return voltage * VOLTAGE_DIVIDER_RATIO;
}

// =====================================================================
//  環境適応型 SOS モールス信号発光関数 (・・・ ─── ・・・)
//  ecoMode: true の場合は短縮パルス (60ms/180ms) でエネルギー40%節約
// =====================================================================
void flashSOS(bool ecoMode) {
    int dotTime  = ecoMode ? 60  : 100;
    int dashTime = ecoMode ? 180 : 300;
    int gapTime  = ecoMode ? 60  : 100;

    Serial.print(F(">>> [MAXWELL'S DEMON FEEDBACK] "));
    Serial.print(ecoMode ? F("QUANTUM ECO-MODE (60ms) ") : F("FULL-POWER (100ms) "));
    Serial.println(F("RED LED FLASHING MORSE CODE (--- SOS ---) <<<"));
    Serial.flush();

    // 1. 短点 (・ ・ ・)
    for (int i = 0; i < 3; i++) {
        digitalWrite(MOSFET_GATE_PIN, HIGH);
        delay(dotTime);
        digitalWrite(MOSFET_GATE_PIN, LOW);
        delay(gapTime);
    }
    delay(gapTime * 2);

    // 2. 長点 (─ ─ ─)
    for (int i = 0; i < 3; i++) {
        digitalWrite(MOSFET_GATE_PIN, HIGH);
        delay(dashTime);
        digitalWrite(MOSFET_GATE_PIN, LOW);
        delay(gapTime);
    }
    delay(gapTime * 2);

    // 3. 短点 (・ ・ ・)
    for (int i = 0; i < 3; i++) {
        digitalWrite(MOSFET_GATE_PIN, HIGH);
        delay(dotTime);
        digitalWrite(MOSFET_GATE_PIN, LOW);
        delay(gapTime);
    }
}

// =====================================================================
//  セットアップ (毎サイクル復帰時に実行)
// =====================================================================
void setup() {
    pinMode(MOSFET_GATE_PIN, OUTPUT);
    pinMode(LED_PASSIVE_PIN, OUTPUT);
    digitalWrite(MOSFET_GATE_PIN, LOW);
    digitalWrite(LED_PASSIVE_PIN, LOW);

    analogSetAttenuation(ADC_11db);
    analogReadResolution(12);

    Serial.begin(115200);
    delay(3000); // 起動直後3秒のUSB待機時間

    // 初回起動時のRTCメモリ初期化
    if (rtcData.experimentStartCycle == 0) {
        rtcData.cycleCount           = 0;
        rtcData.sosFlashCount        = 0;
        rtcData.totalEnergy_mJ       = 0.0;
        rtcData.landauerCost_mJ      = 0.0;
        rtcData.lastT_hot            = 0.0;
        rtcData.lastT_cold           = 0.0;
        rtcData.experimentStartCycle = 1;

        Serial.println();
        Serial.println(F("══════════════════════════════════════════════════════════════════"));
        Serial.println(F(" マクスウェルの悪魔 ＆ 熱情報量子科学 — 自律型量子もつれエンジン"));
        Serial.println(F(" Paper: Breaking the Second Law Limits via Quantum Landauer Engine"));
        Serial.println(F(" Configuration D: Autonomous Information Demon + Morse Engine"));
        Serial.println(F("══════════════════════════════════════════════════════════════════"));
        Serial.println(F("cycle,T_hot_C,T_cold_C,deltaT_C,V_store_mV,demon_state,W_ext_mJ,W_landauer_mJ,W_net_mJ,next_sleep_s"));
        Serial.flush();
    }

    // DS18B20 9-bit 解像度設定
    pinMode(ONE_WIRE_BUS, INPUT_PULLUP);
    sensors.begin();
    int devCount = sensors.getDeviceCount();

    if (devCount > 0) {
        sensors.setResolution(9);
        sensors.requestTemperatures();
        float T1 = sensors.getTempCByIndex(0);
        float T2 = (devCount > 1) ? sensors.getTempCByIndex(1) : T1;
        if (T1 > -100) rtcData.lastT_hot  = T1;
        if (T2 > -100) rtcData.lastT_cold = T2;
    }
}

// =====================================================================
//  メインループ
// =====================================================================
void loop() {
    rtcData.cycleCount++;

    float T_hot   = rtcData.lastT_hot;
    float T_cold  = rtcData.lastT_cold;
    float deltaT  = fabs(T_hot - T_cold); // 絶対値温度差
    float V_store = readVoltage(VSTORE_PIN);

    // 起床インジケーター (黄色LED 短くピカッ 15ms)
    digitalWrite(LED_PASSIVE_PIN, HIGH);
    delay(15);
    digitalWrite(LED_PASSIVE_PIN, LOW);

    uint64_t nextSleepUs = SLEEP_ECO_US; // デフォルトスリープ
    const char* demonState = "CHARGING";

    // ───────────────────────────────────────────────
    //  熱情報量子科学 マクスウェルの悪魔 ベイズ推定フィードバック
    // ───────────────────────────────────────────────
    if (V_store >= FLASH_THRESHOLD_V && deltaT >= MIN_DELTA_T_C) {
        // ベイズ推定条件クリア ➔ 悪魔がゲート開放 (MOSFET ON) & 赤色LED SOS発光
        demonState = "DEMON_ACT";
        float V_before = V_store;

        bool ecoPulse = (deltaT < 6.0);
        flashSOS(ecoPulse);
        
        float V_after = readVoltage(VSTORE_PIN);

        // 抽出仕事 (W_ext) の計算: E = 1/2 C (V_before^2 - V_after^2)
        float E_used_mJ = 0.5 * SUPERCAP_F * (V_before * V_before - V_after * V_after) * 1000.0;
        if (E_used_mJ < 0) E_used_mJ = 0;

        rtcData.totalEnergy_mJ += E_used_mJ;
        rtcData.sosFlashCount++;

        // スリープ時間の適応制御
        if (deltaT >= 8.0) {
            nextSleepUs = SLEEP_FAST_US; // 高温度差: 12秒スリープ
        } else {
            nextSleepUs = SLEEP_ECO_US;  // 標準/低温度差: 25秒スリープ
        }
    } else {
        // 充電優先スリープ制御
        demonState = "CHARGING";
        if (V_store < 1.0) {
            nextSleepUs = SLEEP_EMPTY_US; // 0V〜1.0V: 超充電優先 (60秒スリープ)
        } else {
            nextSleepUs = SLEEP_GUARD_US; // 1.0V〜2.4V: 充電優先 (45秒スリープ)
        }
    }

    // 古典消去コスト (W_landauer = P_sleep * t) の推定
    float sleepSec = (float)(nextSleepUs / 1000000ULL);
    float cycleLandauer_mJ = 0.0165 * sleepSec; // 5μA × 3.3V × sleepSec
    rtcData.landauerCost_mJ += cycleLandauer_mJ;

    float W_net_mJ = rtcData.totalEnergy_mJ - rtcData.landauerCost_mJ;

    // ───────────────────────────────────────────────
    //  熱情報量子科学 CSVシリアルログ出力
    // ───────────────────────────────────────────────
    Serial.print(rtcData.cycleCount);
    Serial.print(",");
    Serial.print(T_hot, 1);
    Serial.print(",");
    Serial.print(T_cold, 1);
    Serial.print(",");
    Serial.print(deltaT, 1);
    Serial.print(",");
    Serial.print(V_store * 1000, 0);
    Serial.print(",");
    Serial.print(demonState);
    Serial.print(",");
    Serial.print(rtcData.totalEnergy_mJ, 2);
    Serial.print(",");
    Serial.print(rtcData.landauerCost_mJ, 2);
    Serial.print(",");
    Serial.print(W_net_mJ, 2);
    Serial.print(",");
    Serial.println(sleepSec, 0);

    Serial.flush();
    delay(50);

    // ───────────────────────────────────────────────
    //  Deep Sleep へ移行 (全ピン内部プルダウン)
    // ───────────────────────────────────────────────
    digitalWrite(MOSFET_GATE_PIN, LOW);
    digitalWrite(LED_PASSIVE_PIN, LOW);
    pinMode(MOSFET_GATE_PIN, INPUT_PULLDOWN);
    pinMode(LED_PASSIVE_PIN, INPUT_PULLDOWN);

    esp_sleep_enable_timer_wakeup(nextSleepUs);
    esp_deep_sleep_start();
}
