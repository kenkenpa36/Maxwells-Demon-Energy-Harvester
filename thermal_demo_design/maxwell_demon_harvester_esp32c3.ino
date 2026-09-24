/*
 * Maxwell's Demon Energy Harvester — ESP32-C3 Deep Sleep 制御コード (コンテストSOSライト版)
 * 構成: TEG 6枚直列 (2×3配列) ＋ 0.9V汎用昇圧 ＋ ESP32-C3 (Deep Sleep 自律制御) ＋ SOSモールス信号発光
 * 
 * 作品名: 『手ぶくろ要らず！体温と熱源で光る 電池ゼロのSOS防災ライト』
 * 
 * 主な機能:
 *   1. 100% 自律自己駆動 (環境発電 TEG 6枚直列 ＋ 1.0F スーパーキャパシタ)
 *   2. Diode-OR ハイブリッド電源回路対応 (USB接続で即時充電・設定、USB抜去で無瞬断自律駆動)
 *   3. ESP32-C3 Deep Sleep 超省エネ待機 (~5μA)
 *   4. マクスウェルの悪魔制御 (温度差 ΔT と 蓄電電圧 Vstore を監視)
 *   5. 赤色LEDによるSOSモールス信号発光 (・・・ ─── ・・・) による高効率情報伝送
 *   6. 黄色LEDによる動作確認インジケーター (極小電力で起床・測定を提示)
 *   7. 環境適応型ピッチ調整 (温度差 ΔT に応じてSOSの発光周期を自律調整)
 * 
 * 接続 (XIAO ESP32-C3):
 *   GPIO2  — DS18B20 温度センサー (OneWire, 4.7kΩプルアップ, 2本: Thot, Tcold)
 *   GPIO3  — MOSFET Gate → 赤色LED (SOSモールス信号制御)
 *   GPIO4  — VSTORE 電圧 ADC (10kΩ/10kΩ 分圧)
 *   GPIO5  — 黄色LED (動作インジケーター)
 *   GND    — 共通 GND
 */

#include <OneWire.h>
#include <DallasTemperature.h>
#include <esp_sleep.h>

// =====================================================================
//  ピン定義 (XIAO ESP32-C3)
// =====================================================================
#define ONE_WIRE_BUS      2    // DS18B20 データピン (GPIO2)
#define MOSFET_GATE_PIN   3    // MOSFET Gate 制御  (GPIO3) → 赤色LED (SOSモールス信号)
#define VSTORE_PIN        4    // VSTORE 電圧 ADC   (GPIO4)
#define LED_PASSIVE_PIN   5    // 黄色LED インジケーター (GPIO5)

// =====================================================================
//  定数設定
// =====================================================================

// --- 電圧閾値 ---
const float FLASH_THRESHOLD_V = 2.5;   // LED点灯開始電圧 (V)
const float LOW_VOLTAGE_GUARD_V = 2.0; // 電圧不足時の保護閾値

// --- 温度差閾値 ---
const float MIN_DELTA_T_C = 3.0;       // 最低必要温度差 (3.0℃以上で動作)

// --- ADC 設定 ---
const float VOLTAGE_DIVIDER_RATIO = 2.0; // 10kΩ/10kΩ 分圧比
const float ADC_REF_VOLTAGE       = 3.3; // 基準電圧 3.3V
const int   ADC_RESOLUTION        = 4095;// 12-bit ADC

// --- スリープ時間設定 (μs 単位) ---
const uint64_t SLEEP_FAST_US  = 10000000ULL; // 高温度差時 (ΔT >= 10℃): 10秒
const uint64_t SLEEP_ECO_US   = 20000000ULL; // 標準/低温度差時 (ΔT < 10℃): 20秒
const uint64_t SLEEP_GUARD_US = 30000000ULL; // 電圧・温度差不足時: 30秒

// --- スーパーキャパシタ容量 ---
const float SUPERCAP_F = 1.0;  // 1.0 ファラド

// =====================================================================
//  RTC メモリ構造体 (Deep Sleep 中もデータを保持)
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
//  SOS モールス信号発光関数 (・・・ ─── ・・・) — 赤色LED
// =====================================================================
void flashSOS() {
    Serial.println(F(">>> [SOS SIGNAL] RED LED FLASHING MORSE CODE (--- SOS ---) <<<"));
    Serial.flush();

    // 1. 短点 (・ ・ ・) : 100ms ON / 100ms OFF
    for (int i = 0; i < 3; i++) {
        digitalWrite(MOSFET_GATE_PIN, HIGH);
        delay(100);
        digitalWrite(MOSFET_GATE_PIN, LOW);
        delay(100);
    }
    delay(200); // 文字間隔

    // 2. 長点 (─ ─ ─) : 300ms ON / 100ms OFF
    for (int i = 0; i < 3; i++) {
        digitalWrite(MOSFET_GATE_PIN, HIGH);
        delay(300);
        digitalWrite(MOSFET_GATE_PIN, LOW);
        delay(100);
    }
    delay(200); // 文字間隔

    // 3. 短点 (・ ・ ・) : 100ms ON / 100ms OFF
    for (int i = 0; i < 3; i++) {
        digitalWrite(MOSFET_GATE_PIN, HIGH);
        delay(100);
        digitalWrite(MOSFET_GATE_PIN, LOW);
        delay(100);
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
    delay(500); // シリアル初期化

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
        Serial.println(F(" 体温SOS防災ライト — マクスウェルの悪魔 制御システム"));
        Serial.println(F(" Configuration D: Self-Powered Red SOS Morse Harvester"));
        Serial.println(F("════════════════════════════════════════════════════"));
        Serial.println(F("cycle,T_hot_C,T_cold_C,deltaT_C,V_store_mV,sos_count,total_energy_mJ,next_sleep_s"));
    }

    // 温度測定
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

// =====================================================================
//  メインループ
// =====================================================================
void loop() {
    rtcData.cycleCount++;

    float T_hot   = rtcData.lastT_hot;
    float T_cold  = rtcData.lastT_cold;
    float deltaT  = T_hot - T_cold;
    float V_store = readVoltage(VSTORE_PIN);

    // 起床インジケーター (黄色LED 短くピカッ)
    digitalWrite(LED_PASSIVE_PIN, HIGH);
    delay(30);
    digitalWrite(LED_PASSIVE_PIN, LOW);

    uint64_t nextSleepUs = SLEEP_ECO_US; // デフォルトスリープ 20秒

    // ───────────────────────────────────────────────
    //  マクスウェルの悪魔 判定 ＆ SOS発光制御
    // ───────────────────────────────────────────────
    if (V_store >= FLASH_THRESHOLD_V && deltaT >= MIN_DELTA_T_C) {
        // 発電電圧と温度差が十分にある場合 ➔ 赤色LEDでSOSモールス信号を発光
        float V_before = V_store;
        
        flashSOS(); // 赤色LED SOS (・・・ ─── ・・・) 点滅
        
        float V_after = readVoltage(VSTORE_PIN);

        // 消費エネルギーの計算: E = 0.5 * C * (V1^2 - V2^2)
        float E_used_mJ = 0.5 * SUPERCAP_F * (V_before * V_before - V_after * V_after) * 1000.0;
        if (E_used_mJ < 0) E_used_mJ = 0;

        rtcData.totalEnergy_mJ += E_used_mJ;
        rtcData.sosFlashCount++;

        // 環境適応型ピッチ調整: 温度差が大きい場合はSOSのペースを上げる
        if (deltaT >= 10.0) {
            nextSleepUs = SLEEP_FAST_US; // 10秒スリープ (ハイペース)
        } else {
            nextSleepUs = SLEEP_ECO_US;  // 20秒スリープ (エコモード)
        }
    } else {
        // 電圧または温度差が不足している場合 ➔ 省エネ待機
        nextSleepUs = SLEEP_GUARD_US;   // 30秒スリープ (ガードモード)
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
    //  Deep Sleep へ移行
    // ───────────────────────────────────────────────
    digitalWrite(MOSFET_GATE_PIN, LOW);
    digitalWrite(LED_PASSIVE_PIN, LOW);
    pinMode(MOSFET_GATE_PIN, INPUT_PULLDOWN);
    pinMode(LED_PASSIVE_PIN, INPUT_PULLDOWN);

    esp_sleep_enable_timer_wakeup(nextSleepUs);
    esp_deep_sleep_start();
}
