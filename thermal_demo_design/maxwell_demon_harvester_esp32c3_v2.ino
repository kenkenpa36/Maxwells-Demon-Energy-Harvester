/*
 * Maxwell's Demon Energy Harvester — ESP32-C3 Ultra-Low Power Adaptive Edition
 * 構成: TEG 6枚直列 (2×3配列) ＋ 0.9V汎用昇圧 ＋ ESP32-C3 (超低消費電力・高発電効率自律制御)
 *
 * 作品名: 『手ぶくろ要らず！体温と熱源で光る 電池ゼロのSOS防災ライト』
 *
 * v2 発電効率向上版 (起床中の無駄なエネルギー消費を削減。旧版 maxwell_demon_harvester_esp32c3.ino は変更せず残置):
 *   1. 起動時の固定 3 秒 USB 待機を廃止。電源投入直後の初回起動のみ 3 秒待ち、
 *      以降は USB ホストを検出した時だけ最大 3 秒 (CDC 準備完了で早期脱出)、
 *      未検出 (自律運転中) は 300 ms のプローブのみ。
 *      → 自律運転時、起床 1 回あたり約 2.7 秒 (≈ 180 mJ) の待機を削減。最大の改善点。
 *   2. CPU クロックを 80 MHz に固定 (160 MHz 比で起床中の消費電流を低減)。
 *   3. DS18B20 2 本のアドレスを RTC メモリにキャッシュし、毎起床のバス探索
 *      (DallasTemperature::begin の 50〜150 ms 遅延) を省略。2 本揃わない間は
 *      キャッシュせず毎起床で再探索する。変換 (94 ms) は USB 待機・ADC 読取と並行実行。
 *   4. 充電中は前回からの充電速度 dV/dt から発光閾値到達時刻を予測して眠る
 *      (無駄な起床を排除)。発光後の微小温度差 (< 3℃) は 45 秒ガードスリープ。
 *   5. センサが 2 本揃わない / 読取に失敗したサイクルは SENSOR_ERR とし、RTC に
 *      残った古い温度差で発光しない (旧版からの継承バグを修正)。
 *   6. 起床中の消費 (W_active) を CSV に追加。行の出力時点で今サイクル分
 *      (起動〜この行の直前 + drain) を含めて出力し、flush 後に実測値を累積する。
 *      W_ext / W_landauer / W_active / W_net_total はいずれも「今サイクルまで」。
 *   7. 判断ロジックを demon_policy.h に分離し、ホスト側でテスト済み
 *      (test/run_tests.sh --coverage --syntax)。
 *
 * 従来からの省エネ機能:
 *   - DS18B20 9-bit 高速変換 (750ms → 93.75ms)
 *   - エコ SOS モールス発光 (微小温度差時は 60ms/180ms パルスで 40% 節約)
 *   - 最低点灯閾値: ΔT >= 0.5℃, Vstore >= 2.4V
 *
 * 接続 (XIAO ESP32-C3):
 *   GPIO2  — DS18B20 温度センサー (OneWire, 4.7kΩプルアップ)
 *   GPIO3  — MOSFET Gate → 赤色LED (SOSモールス信号制御)
 *   GPIO4  — VSTORE 電圧 ADC (10kΩ/10kΩ 分圧)
 *   GPIO5  — 黄色LED (動作確認インジケーター)
 *   GND    — 共通 GND
 *
 * ビルド: demon_policy.h をこの .ino と同じスケッチフォルダに置くこと。
 *         フォルダには .ino を 1 つだけ入れること (Arduino は全 .ino を連結する)。
 *         arduino-esp32 core 2.x (ESP-IDF 4.4) / 3.x (ESP-IDF 5.x) の両方を想定。
 */

#include <OneWire.h>
#include <DallasTemperature.h>
#include <esp_sleep.h>
#include <esp_system.h>        // esp_reset_reason()
#include <esp_idf_version.h>   // ESP_IDF_VERSION
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 0, 0)
#include "driver/usb_serial_jtag.h"  // usb_serial_jtag_is_connected(): SOF 検出 (IDF 5 以降のみ)
constexpr bool HAS_USB_BUS_DETECT = true;
#else
constexpr bool HAS_USB_BUS_DETECT = false;  // core 2.x: CDC 準備完了しか分からない
#endif
#include "demon_policy.h"            // 判断ロジック (ホスト側テスト済み)

// =====================================================================
//  ピン定義 (XIAO ESP32-C3)
// =====================================================================
#define ONE_WIRE_BUS      2    // DS18B20 データピン (GPIO2)
#define MOSFET_GATE_PIN   3    // MOSFET Gate 制御  (GPIO3) → 赤色LED
#define VSTORE_PIN        4    // VSTORE 電圧 ADC   (GPIO4)
#define LED_PASSIVE_PIN   5    // 黄色LED インジケーター (GPIO5)

// =====================================================================
//  定数設定
// =====================================================================
const demon::Config& CFG = demon::DEFAULT_CONFIG;  // 閾値・スリープ・収支パラメータ

// --- 省電力設定 ---
const uint32_t CPU_FREQ_MHZ         = 80;    // USB CDC が動作する最低クロック (PLL 維持)
const uint32_t USB_POLL_INTERVAL_MS = 10;    // ホスト接続検出のポーリング間隔
const uint32_t WAKE_BLINK_MS        = 15;    // 起床インジケーター (黄色LED) 点灯時間
const uint32_t SERIAL_DRAIN_MS      = 50;    // スリープ前にログ送信を完了させる猶予

// --- ADC 設定 ---
const float VOLTAGE_DIVIDER_RATIO = 2.0;  // 10kΩ/10kΩ 分圧比
const float ADC_REF_VOLTAGE       = 3.3;  // 基準電圧 3.3V
const int   ADC_RESOLUTION        = 4095; // 12-bit ADC
const int   ADC_SAMPLES           = 4;    // 平均化サンプル数

// --- センサ ---
const uint8_t MAX_SENSORS        = 2;      // 高温側 / 低温側
const float   SENSOR_INVALID_C   = -100.0; // これ以下は読取失敗 (DEVICE_DISCONNECTED_C = -127)

// =====================================================================
//  RTC メモリ構造体 (Deep Sleep 中も保持。それ以外のリセットでは 0 クリア)
// =====================================================================
RTC_DATA_ATTR struct {
    uint32_t cycleCount;            // 累積ウェイク数
    uint32_t sosFlashCount;         // SOS発光回数 (悪魔のフィードバック作動数)
    float    totalEnergy_mJ;        // 抽出エネルギー累積 W_ext (mJ)
    float    landauerCost_mJ;       // 古典ランダウアー消去コスト W_erase (mJ) = スリープ電力
    float    activeCost_mJ;         // 起床中の消費 W_active (mJ) の実測累積 (完了したサイクルまで)
    float    lastT_hot;             // 高温側温度 (℃)
    float    lastT_cold;            // 低温側温度 (℃)
    float    lastV_store;           // 前回スリープ直前のキャパシタ電圧 (V)
    uint64_t lastSleepUs;           // 前回のスリープ時間 (μs)。0 = 履歴なし
    uint8_t  hostSeen;              // 前回起床時に USB ホストを検出したか
    uint8_t  sensorCount;           // キャッシュ済み DS18B20 の数 (MAX_SENSORS か 0。0 = 次回起床で再探索)
    DeviceAddress sensorAddr[MAX_SENSORS];  // DS18B20 ROM アドレスのキャッシュ
    uint32_t experimentStartCycle;  // 初回起動マーカー
} rtcData;

// =====================================================================
//  温度センサー
// =====================================================================
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
uint32_t g_convStartMs = 0;

// =====================================================================
//  電圧読取り関数
// =====================================================================
float readVoltage(int pin) {
    uint32_t sum = 0;
    for (int i = 0; i < ADC_SAMPLES; i++) {
        sum += analogRead(pin);
    }
    float raw = (float)sum / ADC_SAMPLES;
    float voltage = (raw / (float)ADC_RESOLUTION) * ADC_REF_VOLTAGE;
    return voltage * VOLTAGE_DIVIDER_RATIO;
}

// =====================================================================
//  USB ホスト検出
// =====================================================================

// USB バスにホストがいるか (ケーブルがホストに刺さっているか)。
// IDF 5 以降は SOF 検出で即判定、IDF 4.4 (core 2.x) は CDC 準備完了で代用。
bool usbBusActive() {
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 0, 0)
    return usb_serial_jtag_is_connected();
#else
    return static_cast<bool>(Serial);
#endif
}

// CDC がホスト側アプリ (シリアルモニタ) に開かれ、送信が届く状態か。
// HWCDC::operator bool() は core 2.x / 3.x の両方に存在する。
bool cdcReady() {
    return static_cast<bool>(Serial);
}

// 最大 budgetMs 待つ。allowEarlyExit=true なら CDC 準備完了で即脱出する。
// バス活性を独立に検出できるコア (IDF >= 5) では、ホストが居なければ
// noHostProbeMs で打ち切る。core 2.x では判別できないため予算いっぱい待つ
// (ケーブルを抜いた直後の 1 回だけ 3 秒を消費し、以降は hostSeen=0 で短縮)。
// 戻り値: ホスト (バス活性 or CDC 準備完了) を検出したか。
bool waitForUsbHost(uint32_t budgetMs, bool allowEarlyExit) {
    const uint32_t start = millis();
    bool busActive = false;
    bool ready = false;

    while ((millis() - start) < budgetMs) {
        delay(USB_POLL_INTERVAL_MS);  // SOF 監視の初期値が確定するまで数 ms 必要
        busActive = busActive || usbBusActive();
        ready = cdcReady();
        if (ready && allowEarlyExit) break;
        if (allowEarlyExit && HAS_USB_BUS_DETECT && !busActive &&
            (millis() - start) >= CFG.noHostProbeMs) {
            break;
        }
    }
    return busActive || ready;
}

// =====================================================================
//  温度センサー: 初回探索 (RTC にアドレスをキャッシュ) / 変換開始 / 読み取り
// =====================================================================
void discoverSensors() {
    sensors.begin();
    uint8_t found = sensors.getDeviceCount();
    if (found > MAX_SENSORS) found = MAX_SENSORS;

    uint8_t cached = 0;
    for (uint8_t i = 0; i < found; i++) {
        if (sensors.getAddress(rtcData.sensorAddr[cached], i)) cached++;
    }
    // 高温側・低温側の両方が揃った時だけキャッシュする。揃うまでは毎起床で再探索し、
    // 後から挿した 2 本目を確実に拾う (1 本だけでは温度差が測れず発光もしない)。
    if (cached < MAX_SENSORS) {
        rtcData.sensorCount = 0;
        return;
    }
    rtcData.sensorCount = MAX_SENSORS;
    sensors.setResolution(9);  // DS18B20 の EEPROM に保存されるため初回のみで十分
}

void startTemperatureConversion() {
    pinMode(ONE_WIRE_BUS, INPUT_PULLUP);
    if (rtcData.sensorCount == 0) discoverSensors();
    if (rtcData.sensorCount == 0) return;

    sensors.setWaitForConversion(false);   // 変換完了を待たずに戻る
    sensors.requestTemperatures();         // Skip ROM 一斉変換 (バス探索不要)
    g_convStartMs = millis();
}

// 今サイクルの読取が全プローブで成功した場合のみ true。失敗時はキャッシュを
// 破棄して次回起床で再探索させ、rtcData の温度は更新しない。
bool finishTemperatureRead() {
    if (rtcData.sensorCount == 0) return false;

    delay(demon::remainingConversionWaitMs(CFG.ds18b20ConversionMs, millis() - g_convStartMs));

    float temps[MAX_SENSORS];
    for (uint8_t i = 0; i < rtcData.sensorCount; i++) {
        temps[i] = sensors.getTempC(rtcData.sensorAddr[i]);
        if (temps[i] <= SENSOR_INVALID_C) {
            rtcData.sensorCount = 0;  // 断線/CRC エラー: 次回再探索
            return false;
        }
    }
    rtcData.lastT_hot  = temps[0];
    rtcData.lastT_cold = temps[1];
    return true;
}

// =====================================================================
//  環境適応型 SOS モールス信号発光関数 (・・・ ─── ・・・)
//  パターンと時間は demon_policy.h の定義を使う
// =====================================================================
void flashSOS(bool ecoMode) {
    const demon::MorseTiming t = demon::morseTiming(ecoMode);

    Serial.print(F(">>> [MAXWELL'S DEMON FEEDBACK] "));
    Serial.print(ecoMode ? F("QUANTUM ECO-MODE (60ms) ") : F("FULL-POWER (100ms) "));
    Serial.println(F("RED LED FLASHING MORSE CODE (--- SOS ---) <<<"));
    Serial.flush();

    for (unsigned i = 0; i < demon::SOS_SYMBOL_COUNT; i++) {
        digitalWrite(MOSFET_GATE_PIN, HIGH);
        delay(demon::sosSymbolOnMs(i, t));
        digitalWrite(MOSFET_GATE_PIN, LOW);
        delay(demon::sosGapAfterMs(i, t));
    }
}

// =====================================================================
//  ログ出力
// =====================================================================
void printBanner() {
    Serial.println();
    Serial.println(F("══════════════════════════════════════════════════════════════════"));
    Serial.println(F(" マクスウェルの悪魔 ＆ 熱情報量子科学 — 自律型量子もつれエンジン"));
    Serial.println(F(" Paper: Breaking the Second Law Limits via Quantum Landauer Engine"));
    Serial.println(F(" Configuration D: Autonomous Information Demon + Morse Engine (v2)"));
    Serial.println(F("══════════════════════════════════════════════════════════════════"));
    Serial.println(F("# All energy columns cover completed cycles plus THIS cycle (W_landauer: incl. the sleep that follows;"));
    Serial.println(F("#  W_active / awake_ms: incl. this wake up to, but excluding, the transmission of this row)."));
    Serial.println(F("cycle,T_hot_C,T_cold_C,deltaT_C,V_store_mV,demon_state,W_ext_mJ,W_landauer_mJ,W_net_mJ,next_sleep_s,W_active_mJ,W_net_total_mJ,awake_ms"));
    Serial.flush();
}

// awakeSoFarMs: 今サイクルの起床時間の見込み (この行の送信時間を除く)
void logCycle(float T_hot, float T_cold, float deltaT, float V_store,
              const char* demonState, float sleepSec, uint32_t awakeSoFarMs) {
    float W_active_mJ    = rtcData.activeCost_mJ + demon::activeCost_mJ(awakeSoFarMs, CFG);
    float W_net_mJ       = rtcData.totalEnergy_mJ - rtcData.landauerCost_mJ;
    float W_net_total_mJ = W_net_mJ - W_active_mJ;

    Serial.print(rtcData.cycleCount);         Serial.print(",");
    Serial.print(T_hot, 1);                   Serial.print(",");
    Serial.print(T_cold, 1);                  Serial.print(",");
    Serial.print(deltaT, 1);                  Serial.print(",");
    Serial.print(V_store * 1000, 0);          Serial.print(",");
    Serial.print(demonState);                 Serial.print(",");
    Serial.print(rtcData.totalEnergy_mJ, 2);  Serial.print(",");
    Serial.print(rtcData.landauerCost_mJ, 2); Serial.print(",");
    Serial.print(W_net_mJ, 2);                Serial.print(",");
    Serial.print(sleepSec, 0);                Serial.print(",");
    Serial.print(W_active_mJ, 2);             Serial.print(",");
    Serial.print(W_net_total_mJ, 2);          Serial.print(",");
    Serial.println(awakeSoFarMs);
    Serial.flush();
}

// =====================================================================
//  Deep Sleep へ移行 (全ピン内部プルダウン)
// =====================================================================
void enterDeepSleep(uint64_t sleepUs) {
    digitalWrite(MOSFET_GATE_PIN, LOW);
    digitalWrite(LED_PASSIVE_PIN, LOW);
    pinMode(MOSFET_GATE_PIN, INPUT_PULLDOWN);
    pinMode(LED_PASSIVE_PIN, INPUT_PULLDOWN);

    esp_sleep_enable_timer_wakeup(sleepUs);
    esp_deep_sleep_start();
}

// =====================================================================
//  セットアップ (毎サイクル復帰時に実行)
// =====================================================================
void setup() {
    setCpuFrequencyMhz(CPU_FREQ_MHZ);

    pinMode(MOSFET_GATE_PIN, OUTPUT);
    pinMode(LED_PASSIVE_PIN, OUTPUT);
    digitalWrite(MOSFET_GATE_PIN, LOW);
    digitalWrite(LED_PASSIVE_PIN, LOW);

    analogSetAttenuation(ADC_11db);
    analogReadResolution(12);

    // 先に温度変換を開始し、USB 待機と並行させる
    startTemperatureConversion();

    // RTC が空 = 初回起動 or Deep Sleep 以外のリセット (ブラウンアウト等)。
    // 3 秒の猶予 (早期脱出なし) は電源投入直後の初回起動だけに与える。
    const bool rtcCleared = (rtcData.experimentStartCycle == 0);
    const bool coldStart  = (esp_reset_reason() == ESP_RST_POWERON);
    const bool graceBoot  = rtcCleared && coldStart;

    Serial.begin(115200);
    const uint32_t budgetMs = demon::startupWaitBudgetMs(graceBoot, rtcData.hostSeen != 0, CFG);
    rtcData.hostSeen = waitForUsbHost(budgetMs, !graceBoot) ? 1 : 0;

    if (rtcCleared) {
        rtcData.cycleCount           = 0;
        rtcData.sosFlashCount        = 0;
        rtcData.totalEnergy_mJ       = 0.0;
        rtcData.landauerCost_mJ      = 0.0;
        rtcData.activeCost_mJ        = 0.0;
        rtcData.lastT_hot            = 0.0;
        rtcData.lastT_cold           = 0.0;
        rtcData.lastV_store          = 0.0;
        rtcData.lastSleepUs          = 0;
        rtcData.experimentStartCycle = 1;
        printBanner();
    }
}

// =====================================================================
//  メインループ (1 サイクル実行して Deep Sleep)
// =====================================================================
void loop() {
    rtcData.cycleCount++;

    // 起床インジケーター (黄色LED 短くピカッ)
    digitalWrite(LED_PASSIVE_PIN, HIGH);
    delay(WAKE_BLINK_MS);
    digitalWrite(LED_PASSIVE_PIN, LOW);

    const bool tempValid = finishTemperatureRead();

    float T_hot   = rtcData.lastT_hot;
    float T_cold  = rtcData.lastT_cold;
    float deltaT  = fabs(T_hot - T_cold);
    float V_store = readVoltage(VSTORE_PIN);
    float V_end   = V_store;

    // ───────────────────────────────────────────────
    //  マクスウェルの悪魔 フィードバック判断
    // ───────────────────────────────────────────────
    const demon::Decision decision = demon::decideDemon(V_store, deltaT, CFG, tempValid);
    const char* demonState;
    uint64_t nextSleepUs;

    if (decision.act) {
        demonState = "DEMON_ACT";
        flashSOS(decision.eco);
        V_end = readVoltage(VSTORE_PIN);

        rtcData.totalEnergy_mJ += demon::extractedEnergy_mJ(CFG.supercapF, V_store, V_end);
        rtcData.sosFlashCount++;
        nextSleepUs = demon::selectSleepUs(true, V_store, deltaT, CFG);
    } else {
        demonState = tempValid ? "CHARGING" : "SENSOR_ERR";
        nextSleepUs = demon::predictChargeSleepUs(V_store, rtcData.lastV_store, rtcData.lastSleepUs, CFG);

        // SENSOR_ERR 視覚警告: 黄色LED 3回高速点滅 (通常の1回15msと明確に区別)
        if (!tempValid) {
            for (int i = 0; i < 3; i++) {
                digitalWrite(LED_PASSIVE_PIN, HIGH);
                delay(100);
                digitalWrite(LED_PASSIVE_PIN, LOW);
                delay(100);
            }
        }
    }

    // ───────────────────────────────────────────────
    //  エネルギー収支の更新とログ
    // ───────────────────────────────────────────────
    rtcData.landauerCost_mJ += demon::sleepCost_mJ(nextSleepUs, CFG);
    rtcData.lastV_store      = V_end;
    rtcData.lastSleepUs      = nextSleepUs;

    // この行の送信時間だけは含められないので、drain 込みの見込み値で出力する
    const uint32_t awakeSoFarMs = millis() + SERIAL_DRAIN_MS;
    logCycle(T_hot, T_cold, deltaT, V_store, demonState, demon::sleepSeconds(nextSleepUs), awakeSoFarMs);
    delay(SERIAL_DRAIN_MS);

    // 実測の起床コストを flush 完了後に累積 (ブート ROM 時間は含まない)
    rtcData.activeCost_mJ += demon::activeCost_mJ(millis(), CFG);

    enterDeepSleep(nextSleepUs);
}
