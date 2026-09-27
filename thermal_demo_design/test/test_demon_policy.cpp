// Host-side unit tests for demon_policy.h (pure logic extracted from the
// ESP32-C3 firmware). No Arduino dependency: compile with clang++/g++.
//
//   ./test/run_tests.sh
//
// User journeys covered (see the TDD evidence report):
//   J1 体温でSOSを光らせたい          -> decideDemon
//   J2 無駄な起床を減らしたい          -> selectSleepUs / predictChargeSleepUs
//   J3 USB無し運用で起動待ちを削減     -> startupWaitBudgetMs
//   J4 センサ変換中に他の作業をしたい  -> remainingConversionWaitMs
//   J5 正味仕事を正しく記録したい      -> extractedEnergy / sleepCost / activeCost
//   J6 エコモードで40%節電したい       -> morseOnTimeMs / morseTotalMs

#include "../demon_policy.h"

#include <cmath>
#include <cstdint>
#include <cstdio>

namespace {

int g_failures = 0;
int g_checks = 0;

void check(bool ok, const char* expr, const char* file, int line) {
    ++g_checks;
    if (!ok) {
        ++g_failures;
        std::printf("  FAIL %s:%d  %s\n", file, line, expr);
    }
}

bool nearly(double a, double b, double tol = 1e-3) {
    return std::fabs(a - b) <= tol;
}

#define CHECK(expr) check((expr), #expr, __FILE__, __LINE__)
#define TEST(name) \
    void name(); \
    struct name##_runner { name##_runner() { std::printf("- %s\n", #name); name(); } } name##_instance; \
    void name()

using namespace demon;

const Config& cfg = DEFAULT_CONFIG;

// ───────────────────────── J1: decideDemon ─────────────────────────

TEST(acts_at_full_power_when_voltage_and_delta_t_are_high) {
    Decision d = decideDemon(3.0f, 10.0f, cfg);
    CHECK(d.act);
    CHECK(!d.eco);
}

TEST(acts_in_eco_mode_when_delta_t_is_small_but_valid) {
    Decision d = decideDemon(3.0f, 2.0f, cfg);
    CHECK(d.act);
    CHECK(d.eco);
}

TEST(does_not_act_when_voltage_below_flash_threshold) {
    Decision d = decideDemon(2.39f, 10.0f, cfg);
    CHECK(!d.act);
}

TEST(does_not_act_when_delta_t_below_minimum) {
    Decision d = decideDemon(3.0f, 0.4f, cfg);
    CHECK(!d.act);
}

TEST(acts_exactly_at_threshold_boundaries) {
    Decision d = decideDemon(cfg.flashThresholdV, cfg.minDeltaT, cfg);
    CHECK(d.act);
    CHECK(d.eco);
}

TEST(eco_boundary_switches_to_full_power_at_eco_delta_t) {
    CHECK(decideDemon(3.0f, cfg.ecoDeltaT, cfg).eco == false);
    CHECK(decideDemon(3.0f, cfg.ecoDeltaT - 0.1f, cfg).eco == true);
}

TEST(does_not_act_on_stale_delta_t_when_this_cycle_sensor_read_failed) {
    // Both probes unplugged after a valid 35/20 C cycle: RTC still holds a
    // 15 C difference, but the demon must not flash on stale data.
    Decision d = decideDemon(3.0f, 15.0f, cfg, /*temperatureValid=*/false);
    CHECK(!d.act);
    CHECK(!d.eco);
}

TEST(temperature_validity_defaults_to_true_for_existing_callers) {
    CHECK(decideDemon(3.0f, 15.0f, cfg).act);
    CHECK(decideDemon(3.0f, 15.0f, cfg, true).act);
}

// ───────────────────────── J2: selectSleepUs ─────────────────────────

TEST(after_flash_high_delta_t_sleeps_fast) {
    CHECK(selectSleepUs(true, 3.0f, 8.0f, cfg) == cfg.sleepFastUs);
}

TEST(after_flash_standard_delta_t_sleeps_eco) {
    CHECK(selectSleepUs(true, 3.0f, 3.0f, cfg) == cfg.sleepEcoUs);
    CHECK(selectSleepUs(true, 3.0f, 7.9f, cfg) == cfg.sleepEcoUs);
}

TEST(after_flash_tiny_delta_t_sleeps_guard_to_recharge) {
    // Previously 25 s. A 0.5–3 ℃ gradient recharges slowly, so the demon
    // should stay asleep longer instead of waking into an empty capacitor.
    CHECK(selectSleepUs(true, 3.0f, 2.9f, cfg) == cfg.sleepGuardUs);
}

TEST(charging_with_empty_capacitor_sleeps_longest) {
    CHECK(selectSleepUs(false, 0.9f, 10.0f, cfg) == cfg.sleepEmptyUs);
}

TEST(charging_with_partial_capacitor_sleeps_guard) {
    CHECK(selectSleepUs(false, 1.0f, 10.0f, cfg) == cfg.sleepGuardUs);
    CHECK(selectSleepUs(false, 2.3f, 10.0f, cfg) == cfg.sleepGuardUs);
}

// ───────────────────────── J2: predictChargeSleepUs ─────────────────────────

TEST(predicts_sleep_from_charge_rate_and_rounds_up_to_seconds) {
    // 2.0 V -> 2.2 V over 25 s = 0.008 V/s; need 0.2 V more -> 25 s.
    uint64_t us = predictChargeSleepUs(2.2f, 2.0f, 25000000ULL, cfg);
    CHECK(us == 25000000ULL);
    // 2.0 V -> 2.15 V over 25 s = 0.006 V/s; need 0.25 V -> 41.67 s -> 42 s.
    us = predictChargeSleepUs(2.15f, 2.0f, 25000000ULL, cfg);
    CHECK(us == 42000000ULL);
}

TEST(prediction_is_clamped_to_maximum_sleep_when_charging_slowly) {
    // 1.9 V -> 2.0 V over 25 s; need 0.4 V -> 100 s -> clamp to 60 s.
    CHECK(predictChargeSleepUs(2.0f, 1.9f, 25000000ULL, cfg) == cfg.sleepEmptyUs);
}

TEST(prediction_is_clamped_to_minimum_sleep_when_charging_fast) {
    // 1.9 V -> 2.3 V over 25 s; need 0.1 V -> 6.25 s -> clamp to 12 s.
    CHECK(predictChargeSleepUs(2.3f, 1.9f, 25000000ULL, cfg) == cfg.sleepFastUs);
}

TEST(prediction_uses_maximum_sleep_when_voltage_is_not_rising) {
    CHECK(predictChargeSleepUs(2.0f, 2.0f, 25000000ULL, cfg) == cfg.sleepEmptyUs);
    CHECK(predictChargeSleepUs(1.9f, 2.0f, 25000000ULL, cfg) == cfg.sleepEmptyUs);
}

TEST(prediction_falls_back_to_static_rule_without_history) {
    CHECK(predictChargeSleepUs(2.0f, 0.0f, 0ULL, cfg) == selectSleepUs(false, 2.0f, 10.0f, cfg));
    CHECK(predictChargeSleepUs(0.5f, 0.0f, 0ULL, cfg) == cfg.sleepEmptyUs);
}

TEST(prediction_tolerates_float_representation_error_in_round_up) {
    // 2.2 V -> 2.3 V over 25 s; need 0.1 V. In float arithmetic this comes out
    // as 25.00006 s, which must still round to 25 s, not 26 s.
    CHECK(predictChargeSleepUs(2.3f, 2.2f, 25000000ULL, cfg) == 25000000ULL);
}

TEST(prediction_at_exact_threshold_uses_eco_sleep) {
    CHECK(predictChargeSleepUs(cfg.flashThresholdV, 2.3f, 25000000ULL, cfg) == cfg.sleepEcoUs);
}

TEST(clamp_sleep_bounds_both_ends) {
    CHECK(clampSleepUs(1ULL, cfg) == cfg.sleepFastUs);
    CHECK(clampSleepUs(999000000ULL, cfg) == cfg.sleepEmptyUs);
    CHECK(clampSleepUs(30000000ULL, cfg) == 30000000ULL);
}

TEST(prediction_with_negligible_charge_rate_does_not_overflow) {
    // 1 nV rise over 60 s -> astronomically long estimate: must clamp, not UB.
    CHECK(predictChargeSleepUs(1.000000001f, 1.0f, 60000000ULL, cfg) == cfg.sleepEmptyUs);
}

TEST(prediction_with_voltage_already_above_threshold_uses_eco_sleep) {
    // Capacitor is ready but ΔT was too small to flash: re-check at the
    // standard interval so a hand placed on the plate is noticed without
    // draining the capacitor with rapid wake-ups.
    CHECK(predictChargeSleepUs(2.6f, 2.5f, 25000000ULL, cfg) == cfg.sleepEcoUs);
}

// ───────────────────────── J3: startupWaitBudgetMs ─────────────────────────

TEST(first_boot_waits_full_budget_for_serial_monitor) {
    CHECK(startupWaitBudgetMs(true, false, cfg) == cfg.firstBootWaitMs);
    CHECK(startupWaitBudgetMs(true, true, cfg) == cfg.firstBootWaitMs);
}

TEST(later_wakes_with_host_seen_wait_for_cdc_reenumeration) {
    CHECK(startupWaitBudgetMs(false, true, cfg) == cfg.hostSeenWaitMs);
}

TEST(later_wakes_without_host_only_probe_briefly) {
    CHECK(startupWaitBudgetMs(false, false, cfg) == cfg.noHostProbeMs);
    CHECK(cfg.noHostProbeMs < cfg.hostSeenWaitMs);
    CHECK(cfg.hostSeenWaitMs <= cfg.firstBootWaitMs);
}

// ───────────────────────── J4: remainingConversionWaitMs ─────────────────────────

TEST(remaining_conversion_wait_subtracts_elapsed_time) {
    CHECK(remainingConversionWaitMs(94, 0) == 94);
    CHECK(remainingConversionWaitMs(94, 30) == 64);
}

TEST(remaining_conversion_wait_is_zero_once_elapsed) {
    CHECK(remainingConversionWaitMs(94, 94) == 0);
    CHECK(remainingConversionWaitMs(94, 500) == 0);
}

// ───────────────────────── J5: energy accounting ─────────────────────────

TEST(extracted_energy_follows_half_c_v_squared) {
    // 0.5 * 1 F * (2.5^2 - 2.3^2) = 0.48 J = 480 mJ
    CHECK(nearly(extractedEnergy_mJ(1.0f, 2.5f, 2.3f), 480.0, 0.05));
}

TEST(extracted_energy_is_clamped_to_zero_when_capacitor_charged_during_flash) {
    CHECK(extractedEnergy_mJ(1.0f, 2.3f, 2.5f) == 0.0f);
}

TEST(sleep_cost_is_sleep_power_times_seconds) {
    // 0.0165 mW * 25 s = 0.4125 mJ
    CHECK(nearly(sleepCost_mJ(25000000ULL, cfg), 0.4125, 1e-4));
}

TEST(active_cost_is_active_power_times_awake_time) {
    // 66 mW * 3.0 s = 198 mJ
    CHECK(nearly(activeCost_mJ(3000, cfg), 198.0, 0.01));
    CHECK(activeCost_mJ(0, cfg) == 0.0f);
}

TEST(sleep_seconds_truncates_microseconds) {
    CHECK(sleepSeconds(25000000ULL) == 25.0f);
    CHECK(sleepSeconds(25999999ULL) == 25.0f);
}

// ───────────────────────── J6: Morse timing ─────────────────────────

TEST(eco_morse_saves_forty_percent_led_on_time) {
    unsigned full = morseOnTimeMs(false);
    unsigned eco  = morseOnTimeMs(true);
    CHECK(full == 1500);
    CHECK(eco == 900);
    CHECK(nearly(1.0 - (double)eco / full, 0.40, 1e-9));
}

TEST(morse_total_duration_includes_gaps) {
    CHECK(morseTotalMs(false) == 2800);
    CHECK(morseTotalMs(true) == 1680);
}

TEST(morse_timing_struct_matches_mode) {
    MorseTiming t = morseTiming(true);
    CHECK(t.dotMs == 60 && t.dashMs == 180 && t.gapMs == 60);
    t = morseTiming(false);
    CHECK(t.dotMs == 100 && t.dashMs == 300 && t.gapMs == 100);
}

TEST(sos_pattern_is_three_dots_three_dashes_three_dots) {
    CHECK(SOS_SYMBOL_COUNT == 9);
    for (unsigned i = 0; i < SOS_SYMBOL_COUNT; ++i) {
        bool expectDash = (i >= 3 && i < 6);
        CHECK(sosSymbolIsDash(i) == expectDash);
    }
}

TEST(sos_letter_gap_follows_first_s_and_o_only) {
    const MorseTiming t = morseTiming(false);
    // Ordinary symbol gap after symbols 0,1,3,4,6,7,8; letter gap (3x) after 2 and 5.
    CHECK(sosGapAfterMs(0, t) == t.gapMs);
    CHECK(sosGapAfterMs(2, t) == 3 * t.gapMs);
    CHECK(sosGapAfterMs(5, t) == 3 * t.gapMs);
    CHECK(sosGapAfterMs(8, t) == t.gapMs);
}

TEST(morse_totals_are_derived_from_the_sos_pattern) {
    const MorseTiming t = morseTiming(true);
    unsigned on = 0, total = 0;
    for (unsigned i = 0; i < SOS_SYMBOL_COUNT; ++i) {
        on += sosSymbolOnMs(i, t);
        total += sosSymbolOnMs(i, t) + sosGapAfterMs(i, t);
    }
    CHECK(on == morseOnTimeMs(true));
    CHECK(total == morseTotalMs(true));
}

}  // namespace

int main() {
    std::printf("\n%d checks, %d failures\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}
