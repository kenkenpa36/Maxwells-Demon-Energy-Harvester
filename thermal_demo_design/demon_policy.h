/*
 * demon_policy.h — マクスウェルの悪魔 制御ポリシー (純ロジック)
 *
 * ESP32-C3 ファームウェア (maxwell_demon_harvester_esp32c3_v2.ino) から
 * ハードウェア非依存の判断ロジックだけを切り出したヘッダ。
 * Arduino API に依存しないため、ホスト側 (clang++/g++) で単体テストできる:
 *
 *     ./test/run_tests.sh --coverage
 *
 * Arduino IDE でスケッチをコンパイルする際は、このファイルを .ino と
 * 同じスケッチフォルダに置くこと。Arduino はフォルダ内の全 .ino を連結して
 * ビルドするため、そのフォルダには .ino を 1 つだけ入れること。
 */
#pragma once

#include <stdint.h>

namespace demon {

// =====================================================================
//  設定値 (ハードウェア・実験条件に合わせて調整する定数)
// =====================================================================
struct Config {
    // --- 判定閾値 ---
    float flashThresholdV;   // 発光可能下限電圧 [V]
    float emptyV;            // これ未満は「完全放電」扱い [V]
    float minDeltaT;         // 悪魔が作動する最低温度差 [℃]
    float ecoDeltaT;         // これ未満はエコ (短縮パルス) 発光 [℃]
    float stdDeltaT;         // これ未満は発光後もガードスリープ [℃]
    float fastDeltaT;        // これ以上は発光後に高速スリープ [℃]

    // --- スリープ時間 [μs] ---
    uint64_t sleepFastUs;    // 高温度差時 (最短スリープ)
    uint64_t sleepEcoUs;     // 標準時
    uint64_t sleepGuardUs;   // 微小温度差 / 充電優先
    uint64_t sleepEmptyUs;   // 完全放電時 (最長スリープ)

    // --- エネルギー収支 ---
    float supercapF;         // スーパーキャパシタ容量 [F]
    float sleepPower_mW;     // Deep Sleep 消費電力 (5μA × 3.3V) [mW]
    float activePower_mW;    // 起床中の平均消費電力の推定値 (80MHz, USB CDC) [mW]

    // --- 起動時 USB ホスト待機 [ms] ---
    uint32_t firstBootWaitMs;  // 電源投入直後の初回起動: シリアルモニタを開く猶予 (早期脱出なし)
    uint32_t hostSeenWaitMs;   // 前回ホスト検出済み: CDC 再列挙〜モニタ再接続を待つ上限 (早期脱出あり)
    uint32_t noHostProbeMs;    // 前回ホスト無し (自律運転中): バス活性を確認するプローブのみ

    // --- センサ ---
    uint32_t ds18b20ConversionMs;  // DS18B20 9-bit 変換時間 [ms]
};

constexpr Config DEFAULT_CONFIG = {
    // 判定閾値
    2.4f,   // flashThresholdV
    1.0f,   // emptyV
    0.5f,   // minDeltaT
    6.0f,   // ecoDeltaT
    3.0f,   // stdDeltaT
    8.0f,   // fastDeltaT
    // スリープ [μs]
    10000000ULL,  // sleepFastUs  (10 s)
    25000000ULL,  // sleepEcoUs   (25 s)
    45000000ULL,  // sleepGuardUs (45 s)
    60000000ULL,  // sleepEmptyUs (60 s)
    // エネルギー収支
    1.0f,     // supercapF
    0.0165f,  // sleepPower_mW
    66.0f,    // activePower_mW (20 mA × 3.3 V の推定値)
    // 起動時 USB 待機 [ms]
    3000,  // firstBootWaitMs
    3000,  // hostSeenWaitMs  (旧版の固定 3 秒と同等。ホスト接続で早期脱出)
    300,   // noHostProbeMs
    // センサ
    94,    // ds18b20ConversionMs (9-bit: 93.75 ms)
};

// =====================================================================
//  発光判断 (ベイズ推定フィードバックの古典的近似)
// =====================================================================
struct Decision {
    bool act;  // true: ゲート開放 (MOSFET ON) して SOS 発光
    bool eco;  // true: 短縮パルスで発光 (微小温度差時)
};

// temperatureValid: 今サイクルの温度読取が両プローブとも成功したか。
// false の場合 deltaT は前回値 (RTC 残留) なので、決して発光しない。
inline Decision decideDemon(float vStore, float deltaT, const Config& c, bool temperatureValid = true) {
    Decision d = {false, false};
    if (!temperatureValid) return d;
    if (vStore < c.flashThresholdV || deltaT < c.minDeltaT) return d;
    d.act = true;
    d.eco = (deltaT < c.ecoDeltaT);
    return d;
}

// =====================================================================
//  スリープ時間の決定
// =====================================================================

// 静的ルール: 発光した場合は一律 sleepFastUs、充電中は残電圧で決める。
inline uint64_t selectSleepUs(bool acted, float vStore, float deltaT, const Config& c) {
    if (!acted) {
        return (vStore < c.emptyV) ? c.sleepEmptyUs : c.sleepGuardUs;
    }
    // 発光後は一律 sleepFastUs (10 s) で再起床。エネルギー不足なら
    // 次サイクルの decideDemon が CHARGING に回すため過放電は起きない。
    (void)deltaT;  // 未使用警告を抑制
    return c.sleepFastUs;
}

inline uint64_t clampSleepUs(uint64_t us, const Config& c) {
    if (us < c.sleepFastUs)  return c.sleepFastUs;
    if (us > c.sleepEmptyUs) return c.sleepEmptyUs;
    return us;
}

// float→double 変換の表現誤差 (数十 μs 相当) を切り上げ判定で無視する許容値 [s]
constexpr double SLEEP_ROUNDING_TOLERANCE_S = 1e-3;

// 充電中の予測スリープ: 前回サイクルからの充電速度 dV/dt を使い、
// 発光閾値に達するまでの時間だけ眠る (無駄な起床を排除する)。
//   vNow        : 今回起床時の電圧
//   vPrev       : 前回スリープ直前の電圧
//   prevSleepUs : 前回のスリープ時間 (0 = 履歴なし → 静的ルール)
inline uint64_t predictChargeSleepUs(float vNow, float vPrev, uint64_t prevSleepUs, const Config& c) {
    if (prevSleepUs == 0) return selectSleepUs(false, vNow, 0.0f, c);
    // 電圧は足りているが温度差不足: 手が触れた時に応答できるよう標準間隔で再確認
    if (vNow >= c.flashThresholdV) return c.sleepEcoUs;

    const double dv = static_cast<double>(vNow) - static_cast<double>(vPrev);
    if (dv <= 0.0) return c.sleepEmptyUs;  // 充電されていない: 最長スリープ

    const double ratePerSec = dv / (static_cast<double>(prevSleepUs) / 1e6);
    const double needV = static_cast<double>(c.flashThresholdV) - static_cast<double>(vNow);
    const double secs = needV / ratePerSec;

    // 最長スリープ以上ならキャストせずクランプ (巨大値の uint64 変換は未定義動作)
    const double maxSecs = static_cast<double>(c.sleepEmptyUs) / 1e6;
    if (secs >= maxSecs) return c.sleepEmptyUs;

    uint64_t wholeSecs = static_cast<uint64_t>(secs + SLEEP_ROUNDING_TOLERANCE_S);
    if (static_cast<double>(wholeSecs) < secs - SLEEP_ROUNDING_TOLERANCE_S) ++wholeSecs;  // 切り上げ
    return clampSleepUs(wholeSecs * 1000000ULL, c);
}

inline float sleepSeconds(uint64_t sleepUs) {
    return static_cast<float>(sleepUs / 1000000ULL);
}

// =====================================================================
//  起動時 USB ホスト待機の予算
// =====================================================================
inline uint32_t startupWaitBudgetMs(bool isFirstBoot, bool hostSeenLastCycle, const Config& c) {
    if (isFirstBoot) return c.firstBootWaitMs;
    return hostSeenLastCycle ? c.hostSeenWaitMs : c.noHostProbeMs;
}

// =====================================================================
//  センサ変換の残り待ち時間 (変換中に他の作業を並行させる)
// =====================================================================
inline uint32_t remainingConversionWaitMs(uint32_t conversionMs, uint32_t elapsedMs) {
    return (elapsedMs >= conversionMs) ? 0u : (conversionMs - elapsedMs);
}

// =====================================================================
//  エネルギー収支
// =====================================================================

// 抽出仕事 W_ext = 1/2 C (V_before^2 - V_after^2) [mJ]。発光中に充電が
// 上回った場合は 0 とする。
inline float extractedEnergy_mJ(float capacitanceF, float vBefore, float vAfter) {
    const float joules = 0.5f * capacitanceF * (vBefore * vBefore - vAfter * vAfter);
    return (joules < 0.0f) ? 0.0f : joules * 1000.0f;
}

// 古典ランダウアー消去コストの近似: スリープ中の待機電力 × 時間 [mJ]
inline float sleepCost_mJ(uint64_t sleepUs, const Config& c) {
    return c.sleepPower_mW * (static_cast<float>(sleepUs) / 1e6f);
}

// 起床中 (測定・発光・ログ) の消費 [mJ]。悪魔の「情報処理コスト」の実体。
inline float activeCost_mJ(uint32_t awakeMs, const Config& c) {
    return c.activePower_mW * (static_cast<float>(awakeMs) / 1000.0f);
}

// =====================================================================
//  SOS モールス発光のタイミング (・・・ ─── ・・・)
//  パターンはここで一度だけ定義し、発光関数と所要時間計算の両方が参照する。
// =====================================================================
struct MorseTiming {
    unsigned dotMs;
    unsigned dashMs;
    unsigned gapMs;
};

inline MorseTiming morseTiming(bool ecoMode) {
    return ecoMode ? MorseTiming{60u, 180u, 60u} : MorseTiming{100u, 300u, 100u};
}

constexpr unsigned SOS_SYMBOL_COUNT   = 9;  // S(3) + O(3) + S(3)
constexpr unsigned SOS_LETTER_SYMBOLS = 3;  // 1 文字あたりの符号数

// 符号 i (0..8) が長点か: 中央の 3 つ (O) が長点
inline bool sosSymbolIsDash(unsigned i) {
    return i >= SOS_LETTER_SYMBOLS && i < 2 * SOS_LETTER_SYMBOLS;
}

// 符号 i の点灯時間
inline unsigned sosSymbolOnMs(unsigned i, const MorseTiming& t) {
    return sosSymbolIsDash(i) ? t.dashMs : t.dotMs;
}

// 符号 i の後の消灯時間: 通常 1 ギャップ、文字末 (最終文字を除く) は 3 ギャップ
inline unsigned sosGapAfterMs(unsigned i, const MorseTiming& t) {
    const bool letterEnd = (i % SOS_LETTER_SYMBOLS == SOS_LETTER_SYMBOLS - 1);
    const bool lastSymbol = (i + 1 >= SOS_SYMBOL_COUNT);
    return (letterEnd && !lastSymbol) ? 3u * t.gapMs : t.gapMs;
}

// LED 点灯時間の合計
inline unsigned morseOnTimeMs(bool ecoMode) {
    const MorseTiming t = morseTiming(ecoMode);
    unsigned total = 0;
    for (unsigned i = 0; i < SOS_SYMBOL_COUNT; ++i) total += sosSymbolOnMs(i, t);
    return total;
}

// 発光シーケンス全体の所要時間 (点灯 + 消灯)
inline unsigned morseTotalMs(bool ecoMode) {
    const MorseTiming t = morseTiming(ecoMode);
    unsigned total = 0;
    for (unsigned i = 0; i < SOS_SYMBOL_COUNT; ++i) total += sosSymbolOnMs(i, t) + sosGapAfterMs(i, t);
    return total;
}

}  // namespace demon
