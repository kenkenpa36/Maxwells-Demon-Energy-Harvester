/*
 * Maxwell's Demon Energy Harvester — Arduino制御コード
 * 
 * プロジェクト: Macroscopic Quantum Entanglement Engine 検証デバイス
 * 論文: "Breaking the Second Law Limits: From Autonomous Maxwell's Demons 
 *        to Quantum Landauer Energy Harvesters"
 * 
 * 概要:
 *   体温と外気温の温度差（ΔT≈5〜15℃）からペルチェ素子で発電し、
 *   Arduino（マクスウェルの悪魔）がフィードバック制御することで
 *   エネルギー抽出効率がどう変わるかを検証する。
 * 
 * 実験モード:
 *   Phase A (30秒): Feedback OFF — LED_passive が常時接続（暗い/消灯）
 *   Phase B (30秒): Feedback ON  — Arduino が蓄電量を監視し最適タイミングでLED点灯
 * 
 * 接続:
 *   D2  — DS18B20 温度センサー (OneWire, 4.7kΩプルアップ)
 *   D3  — MOSFET Gate (IRLZ44N) → LED_demon制御
 *   D5  — LED_passive (比較用、常時ON)
 *   A0  — VSTORE電圧モニタ (10kΩ/10kΩ分圧)
 *   A1  — VOUT電圧モニタ (10kΩ/10kΩ分圧)
 *   GND — 共通GND
 *   USB — Arduino電源（5V）= 悪魔のエネルギー源
 */

#include <OneWire.h>
#include <DallasTemperature.h>

// ===== ピン定義 =====
#define ONE_WIRE_BUS    2    // DS18B20 データピン
#define MOSFET_GATE_PIN 3    // MOSFET Gate (PWM対応)
#define LED_PASSIVE_PIN 5    // LED_passive (比較用)
#define VSTORE_PIN      A0   // スーパーキャパシタ電圧
#define VOUT_PIN        A1   // VOUT電圧

// ===== 定数 =====
// 分圧比 (10kΩ / 10kΩ → 実電圧 = 読取値 × 2)
const float VOLTAGE_DIVIDER_RATIO = 2.0;
const float ADC_REF_VOLTAGE = 5.0;
const int   ADC_RESOLUTION = 1023;

// LED点灯閾値: キャパシタ電圧がこの値を超えたらパルス発光
const float FLASH_THRESHOLD_V = 2.5;   // LED Vf + 余裕
// LED消灯閾値: この電圧まで放電したらパルス停止
const float FLASH_CUTOFF_V = 1.8;
// パルス持続時間 (ms)
const int   FLASH_DURATION_MS = 100;

// 実験フェーズ切替時間 (ms)
const unsigned long PHASE_DURATION_MS = 30000; // 30秒

// Arduino消費電力推定 (mW)
const float ARDUINO_POWER_MW = 150.0;  // 5V × 30mA 典型値

// ===== 温度センサー =====
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// ===== 状態変数 =====
bool feedbackMode = false;          // true = Feedback ON (悪魔モード)
unsigned long phaseStartTime = 0;
unsigned long experimentStartTime = 0;

// 計測カウンター
int flashCount_passive = 0;         // Passive LED点灯回数
int flashCount_demon = 0;           // Demon LED点灯回数
float totalEnergy_passive_mJ = 0;   // Passive 抽出エネルギー (mJ)
float totalEnergy_demon_mJ = 0;     // Demon 抽出エネルギー (mJ)
float totalDemonCost_mJ = 0;        // 悪魔のコスト (mJ)

int phaseCount = 0;                 // フェーズ番号

// ===== セットアップ =====
void setup() {
    Serial.begin(9600);
    
    pinMode(MOSFET_GATE_PIN, OUTPUT);
    pinMode(LED_PASSIVE_PIN, OUTPUT);
    
    digitalWrite(MOSFET_GATE_PIN, LOW);
    digitalWrite(LED_PASSIVE_PIN, LOW);
    
    sensors.begin();
    
    Serial.println(F(""));
    Serial.println(F("============================================"));
    Serial.println(F(" Maxwell's Demon Energy Harvester v1.0"));
    Serial.println(F(" 情報エンジン検証デバイス"));
    Serial.println(F("============================================"));
    Serial.println(F(""));
    Serial.println(F("論文: Breaking the Second Law Limits"));
    Serial.println(F("検証: 体温温度差からの情報フィードバック発電"));
    Serial.println(F(""));
    Serial.println(F("Phase A (30s): Feedback OFF — 悪魔なし（受動的）"));
    Serial.println(F("Phase B (30s): Feedback ON  — 悪魔あり（能動的）"));
    Serial.println(F("============================================"));
    Serial.println(F(""));
    Serial.println(F("time_s,phase,T_hot_C,T_cold_C,deltaT_C,V_store_mV,V_out_mV,flash_passive,flash_demon,E_passive_mJ,E_demon_mJ,demon_cost_mJ,net_work_mJ"));
    
    experimentStartTime = millis();
    phaseStartTime = millis();
    feedbackMode = false;
    phaseCount = 0;
}

// ===== 電圧読取 =====
float readVoltage(int pin) {
    int raw = analogRead(pin);
    float voltage = (raw / (float)ADC_RESOLUTION) * ADC_REF_VOLTAGE;
    return voltage * VOLTAGE_DIVIDER_RATIO;  // 分圧補正
}

// ===== メインループ =====
void loop() {
    unsigned long now = millis();
    float elapsed_s = (now - experimentStartTime) / 1000.0;
    
    // ─── フェーズ切替 ───
    if (now - phaseStartTime >= PHASE_DURATION_MS) {
        // フェーズ終了時のサマリー出力
        printPhaseSummary();
        
        // フェーズ切替
        feedbackMode = !feedbackMode;
        phaseStartTime = now;
        phaseCount++;
        
        // LED/MOSFETリセット
        digitalWrite(MOSFET_GATE_PIN, LOW);
        digitalWrite(LED_PASSIVE_PIN, LOW);
        
        Serial.println(F(""));
        if (feedbackMode) {
            Serial.println(F(">>> Phase B 開始: Feedback ON（悪魔がフィードバック制御）"));
        } else {
            Serial.println(F(">>> Phase A 開始: Feedback OFF（受動的接続のみ）"));
        }
        Serial.println(F(""));
    }
    
    // ─── 温度測定 ───
    sensors.requestTemperatures();
    float T_hot  = sensors.getTempCByIndex(0);  // 高温側（体温面）
    float T_cold = sensors.getTempCByIndex(1);  // 低温側（外気面）
    float deltaT = T_hot - T_cold;
    
    // ─── 電圧測定 ───
    float V_store = readVoltage(VSTORE_PIN);  // キャパシタ電圧
    float V_out   = readVoltage(VOUT_PIN);    // VOUT電圧
    
    // ─── 制御ロジック ───
    if (!feedbackMode) {
        // ===== Phase A: Feedback OFF =====
        // LED_passive は常時接続（VOUT直結）
        // MOSFET は常にOFF
        digitalWrite(LED_PASSIVE_PIN, HIGH);
        digitalWrite(MOSFET_GATE_PIN, LOW);
        
        // V_out が LED Vf を超えていれば光っている
        if (V_out > 1.8) {
            // LED電流推定: (V_out - V_LED) / R1
            float I_led_A = (V_out - 1.8) / 330.0;  // 330Ω
            float P_led_mW = V_out * I_led_A * 1000.0;
            totalEnergy_passive_mJ += P_led_mW * 0.5 / 1000.0;  // 0.5秒間隔
            flashCount_passive++;
        }
    } else {
        // ===== Phase B: Feedback ON (マクスウェルの悪魔) =====
        // Arduinoがキャパシタ電圧を監視し、
        // 十分にエネルギーが蓄積されたらMOSFETを開いてLEDをパルス発光
        
        digitalWrite(LED_PASSIVE_PIN, LOW);  // 比較用LEDはOFF
        
        /*
         * 悪魔のフィードバック制御アルゴリズム
         * 
         * 論文との対応:
         *   - V_store の監視  ←→  量子状態の測定 (dy_t)
         *   - 閾値判定        ←→  ベイズ推定 (事後確率 P の計算)
         *   - MOSFET ON/OFF   ←→  トンネル障壁の開閉 (kappa_ON/OFF)
         *   - LEDパルス発光   ←→  仕事の抽出 (W_ext)
         * 
         * シミュレーションコード対応箇所:
         *   simulate_macroscopic_quantum_engine.py L50-L65
         *   if P[0] > 0.5:     → if (V_store < THRESHOLD):
         *       kappaL = ON    →     MOSFET = OFF (蓄電中)
         *   else:              → else:
         *       kappaR = ON    →     MOSFET = ON  (放電=仕事抽出)
         */
        
        if (V_store >= FLASH_THRESHOLD_V) {
            // 十分なエネルギーが蓄積された → ゲートを開いてLED点灯!
            digitalWrite(MOSFET_GATE_PIN, HIGH);
            delay(FLASH_DURATION_MS);
            digitalWrite(MOSFET_GATE_PIN, LOW);
            
            flashCount_demon++;
            
            // 抽出エネルギー計算: E = 0.5 * C * (V1² - V2²)
            float V_after = readVoltage(VSTORE_PIN);
            float E_flash_mJ = 0.5 * 0.47 * (V_store * V_store - V_after * V_after) * 1000.0;
            totalEnergy_demon_mJ += E_flash_mJ;
        }
        
        // 悪魔のコスト（Arduino消費電力）を累積
        totalDemonCost_mJ += ARDUINO_POWER_MW * 0.5 / 1000.0;  // 0.5秒間隔
    }
    
    // ─── データ出力 (CSV形式) ───
    Serial.print(elapsed_s, 1);
    Serial.print(",");
    Serial.print(feedbackMode ? "B_ON" : "A_OFF");
    Serial.print(",");
    Serial.print(T_hot, 1);
    Serial.print(",");
    Serial.print(T_cold, 1);
    Serial.print(",");
    Serial.print(deltaT, 1);
    Serial.print(",");
    Serial.print(V_store * 1000, 0);  // mV
    Serial.print(",");
    Serial.print(V_out * 1000, 0);    // mV
    Serial.print(",");
    Serial.print(flashCount_passive);
    Serial.print(",");
    Serial.print(flashCount_demon);
    Serial.print(",");
    Serial.print(totalEnergy_passive_mJ, 3);
    Serial.print(",");
    Serial.print(totalEnergy_demon_mJ, 3);
    Serial.print(",");
    Serial.print(totalDemonCost_mJ, 3);
    Serial.print(",");
    Serial.println(totalEnergy_demon_mJ - totalDemonCost_mJ, 3);
    
    delay(500);  // 0.5秒間隔で測定
}

// ===== フェーズ終了サマリー =====
void printPhaseSummary() {
    Serial.println(F(""));
    Serial.println(F("────────────────────────────────────────"));
    
    if (!feedbackMode) {
        Serial.println(F("【Phase A 結果: Feedback OFF（悪魔なし）】"));
        Serial.print(F("  LED_passive 点灯時間: "));
        Serial.print(flashCount_passive * 0.5);
        Serial.println(F(" 秒"));
        Serial.print(F("  抽出エネルギー: "));
        Serial.print(totalEnergy_passive_mJ, 3);
        Serial.println(F(" mJ"));
        Serial.print(F("  悪魔のコスト: 0 mJ"));
        Serial.println(F(""));
        Serial.print(F("  正味仕事: "));
        Serial.print(totalEnergy_passive_mJ, 3);
        Serial.println(F(" mJ"));
    } else {
        Serial.println(F("【Phase B 結果: Feedback ON（悪魔あり）】"));
        Serial.print(F("  LED_demon パルス回数: "));
        Serial.println(flashCount_demon);
        Serial.print(F("  抽出エネルギー: "));
        Serial.print(totalEnergy_demon_mJ, 3);
        Serial.println(F(" mJ"));
        Serial.print(F("  悪魔のコスト (Arduino消費): "));
        Serial.print(totalDemonCost_mJ, 3);
        Serial.println(F(" mJ"));
        Serial.println(F(""));
        
        float netWork = totalEnergy_demon_mJ - totalDemonCost_mJ;
        Serial.print(F("  ★ 正味仕事 = 抽出仕事 - 悪魔コスト = "));
        Serial.print(netWork, 3);
        Serial.println(F(" mJ"));
        
        if (netWork < 0) {
            Serial.println(F(""));
            Serial.println(F("  → 正味仕事 < 0: 古典的ランダウアー限界の実証!"));
            Serial.println(F("    悪魔（Arduino）のコストが抽出仕事を上回っている。"));
            Serial.println(F("    論文の主張: 量子もつれを使えばこのコストが負に反転し、"));
            Serial.println(F("    純粋な発電が可能になる。"));
        }
    }
    Serial.println(F("────────────────────────────────────────"));
}
