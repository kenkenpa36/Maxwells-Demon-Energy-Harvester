/*
 * Maxwell's Demon Energy Harvester — ESP32-C3 Ultra-Low Power Adaptive Edition
 * 構成: TEG 6枚直列 (2×3配列) ＋ 0.9V汎用昇圧 ＋ ESP32-C3 (超低消費電力・高発電効率自律制御)
 * 
 * 作品名: 『手ぶくろ要らず！体温と熱源で光る 電池ゼロのSOS防災ライト』
 * 
 * 微小温度差（ΔT < 3℃〜5℃）対応 発電効率向上の新アルゴリズム:
 *   1. CPUクロックの動的低減 (160MHz ➔ 80MHz: 起床時消費電流を約40%カット)
 *   2. DS18B20 9-bit高速変換 (変換時間を750ms ➔ 93.75msへ短縮、起床時間を8分位1に削減)
 *   3. 低電圧・微小温度差時のスマート拡張スリープ (45秒〜60秒へ自動延長、無駄な起床を徹底防止)
 *   4. エコSOSモールス発光 (微小温度差時は60ms/180msの省エネ短縮パルスでエネルギー40%節約)
 *   5. 最低点灯閾値の柔軟化 (ΔT >= 2.0℃、Vstore >= 2.4Vから動的動作サポート)
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
const float MIN_DELTA_T_C         = 2.0;  // 最低有効温度差 (2.0℃の微熱でも動作)

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
    uint32_t sosFlashCount;         // SOS発光回数
    float    totalEnergy_mJ;        // 抽出エネルギー累積 (mJ)
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

    Serial.print(F(">>> [SOS SIGNAL] "));
    Serial.print(ecoMode ? F("ECO-MODE (60ms) ") : F("FULL-POWER (100ms) "));
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
    // ⚡ 発電効率向上 ①: CPUクロックを 160MHz ➔ 80MHz へ下げて起床時消費電力を大幅削減
    setCpuFrequencyMhz(80);

    pinMode(MOSFET_GATE_PIN, OUTPUT);
    pinMode(LED_PASSIVE_PIN, OUTPUT);
    digitalWrite(MOSFET_GATE_PIN, LOW);
    digitalWrite(LED_PASSIVE_PIN, LOW);

    analogSetAttenuation(ADC_11db);
    analogReadResolution(12);

    Serial.begin(115200);

    // 初回起動時のRTCメモリ初期化
    if (rtcData.experimentStartCycle == 0) {
        rtcData.cycleCount           = 0;
        rtcData.sosFlashCount        = 0;
        rtcData.totalEnergy_mJ       = 0.0;
        rtcData.lastT_hot            = 0.0;
        rtcData.lastT_cold           = 0.0;
        rtcData.experimentStartCycle = 1;

        Serial.println();
        Serial.println(F("════════════════════════════════════════════════════"));
        Serial.println(F(" 体温SOS防災ライト — 高発電効率・環境適応システム"));
        Serial.println(F(" Configuration D: Ultra-Low Power Adaptive Morse Engine"));
        Serial.println(F("════════════════════════════════════════════════════"));
        Serial.println(F("cycle,T_hot_C,T_cold_C,deltaT_C,V_store_mV,sos_count,total_energy_mJ,next_sleep_s"));
    }

    // ⚡ 発電効率向上 ②: DS18B20 9-bit 解像度設定 (変換時間を 750ms ➔ 93ms に短縮)
    pinMode(ONE_WIRE_BUS, INPUT_PULLUP);
    sensors.begin();
    int devCount = sensors.getDeviceCount();

    if (devCount > 0) {
        sensors.setResolution(9); // 9-bit 高速測定モード
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
    float deltaT  = T_hot - T_cold;
    float V_store = readVoltage(VSTORE_PIN);

    // 起床インジケーター (黄色LED 短くピカッ 15ms)
    digitalWrite(LED_PASSIVE_PIN, HIGH);
    delay(15);
    digitalWrite(LED_PASSIVE_PIN, LOW);

    uint64_t nextSleepUs = SLEEP_ECO_US; // デフォルトスリープ

    // ───────────────────────────────────────────────
    //  発電効率最適化 マクスウェルの悪魔 判定ロジック
    // ───────────────────────────────────────────────
    if (V_store >= FLASH_THRESHOLD_V && deltaT >= MIN_DELTA_T_C) {
        // 条件クリア ➔ 赤色LED SOSモールス信号発光
        float V_before = V_store;

        // 微小温度差（2.0℃〜6.0℃）時はエコモード（短縮パルス）で消費エネルギーを40%削減
        bool ecoPulse = (deltaT < 6.0);
        flashSOS(ecoPulse);
        
        float V_after = readVoltage(VSTORE_PIN);

        // 消費エネルギーの計算
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
        // ⚡ 発電効率向上 ③: 充電優先スリープ制御
        // 電圧が低い場合や微小温度差時はスリープを45秒〜60秒に延長し、蓄電を最優先
        if (V_store < 1.0) {
            nextSleepUs = SLEEP_EMPTY_US; // 0V〜1.0V: 超充電優先 (60秒スリープ)
        } else {
            nextSleepUs = SLEEP_GUARD_US; // 1.0V〜2.4V: 充電優先 (45秒スリープ)
        }
    }

    // ───────────────────────────────────────────────
    //  シリアルログ出力 (CSV形式)
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
    Serial.print(rtcData.sosFlashCount);
    Serial.print(",");
    Serial.print(rtcData.totalEnergy_mJ, 2);
    Serial.print(",");
    Serial.println((float)(nextSleepUs / 1000000ULL), 0);

    Serial.flush();

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
