// Host-side integration tests for maxwell_demon_harvester_esp32c3_v2.ino.
//
// The sketch is compiled as ordinary C++ against the stateful fakes in
// test/stubs/ and driven through setup()/loop(), one call pair per wake.
// Built twice by run_tests.sh: -DSTUB_IDF_MAJOR=4 (arduino-esp32 2.x) and
// -DSTUB_IDF_MAJOR=5 (arduino-esp32 3.x).

#include "stubs/Arduino.h"
#include "../maxwell_demon_harvester_esp32c3_v2.ino"

#include <cmath>
#include <cstdio>
#include <sstream>
#include <string>
#include <vector>

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

#define CHECK(expr) check((expr), #expr, __FILE__, __LINE__)
#define TEST(name) \
    void name(); \
    struct name##_runner { name##_runner() { std::printf("- %s\n", #name); name(); } } name##_instance; \
    void name()

// ───────────────────────── helpers ─────────────────────────

using RtcType = decltype(rtcData);

// Cold power-on: RTC memory zeroed, fake state fresh, reset reason POWERON.
void powerOn() {
    rtcData = RtcType{};
    fake::reset();
    fake::state().resetReason = ESP_RST_POWERON;
}

// Wake from deep sleep: RTC preserved, millis restarts at 0, buffers cleared.
void wake() {
    fake::State& s = fake::state();
    s.nowMs = 0;
    s.serialOut.clear();
    s.pinWrites.clear();
    s.sleepUs = 0;
    s.deepSleepCalls = 0;
    s.beginCalls = 0;
    s.requestCalls = 0;
    s.resetReason = ESP_RST_DEEPSLEEP;
}

void setStoreVoltage(float volts) {
    // readVoltage(): raw / 4095 * 3.3 * 2
    fake::state().adcRaw = static_cast<int>(std::lround(volts / 6.6 * 4095.0));
}

void setProbes(uint8_t count, float hot, float cold) {
    fake::State& s = fake::state();
    s.deviceCount = count;
    s.temps[0] = hot;
    s.temps[1] = cold;
    s.readFails = false;
}

void runCycle() {
    setup();
    loop();
}

int gateHighCount() {
    int n = 0;
    for (const auto& w : fake::state().pinWrites) {
        if (w.first == MOSFET_GATE_PIN && w.second == HIGH) ++n;
    }
    return n;
}

// Last CSV data row (starts with a digit), split on ','.
std::vector<std::string> lastCsvRow() {
    std::istringstream in(fake::state().serialOut);
    std::string line, last;
    while (std::getline(in, line)) {
        if (!line.empty() && line[0] >= '0' && line[0] <= '9') last = line;
    }
    std::vector<std::string> cols;
    std::istringstream row(last);
    std::string col;
    while (std::getline(row, col, ',')) cols.push_back(col);
    return cols;
}

enum CsvCol { COL_CYCLE, COL_T_HOT, COL_T_COLD, COL_DELTA_T, COL_V_STORE, COL_STATE, COL_W_EXT,
              COL_W_LANDAUER, COL_W_NET, COL_NEXT_SLEEP, COL_W_ACTIVE, COL_W_NET_TOTAL, COL_AWAKE_MS,
              COL_COUNT };

bool contains(const std::string& hay, const char* needle) { return hay.find(needle) != std::string::npos; }

#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 0, 0)
constexpr bool kHasBusDetect = true;
#else
constexpr bool kHasBusDetect = false;
#endif

// ───────────────────────── startup USB wait ─────────────────────────

TEST(first_power_on_waits_full_grace_and_prints_banner) {
    powerOn();
    fake::state().cdcReadyAtMs = 1000;   // user opens the monitor after 1 s
    setProbes(2, 35.0f, 20.0f);
    setStoreVoltage(1.5f);

    setup();

    CHECK(fake::state().nowMs >= CFG.firstBootWaitMs);          // no early exit on first boot
    CHECK(fake::state().nowMs < CFG.firstBootWaitMs + 100);
    CHECK(rtcData.hostSeen == 1);
    CHECK(contains(fake::state().serialOut, "cycle,T_hot_C"));
    CHECK(fake::state().cpuMhz == CPU_FREQ_MHZ);
}

TEST(brownout_with_cleared_rtc_gets_no_grace_period) {
    powerOn();
    fake::state().resetReason = ESP_RST_BROWNOUT;
    setProbes(2, 35.0f, 20.0f);

    setup();

    CHECK(fake::state().nowMs <= CFG.noHostProbeMs + 50);
    CHECK(rtcData.hostSeen == 0);
}

TEST(wake_without_host_only_probes_briefly) {
    powerOn();
    setProbes(2, 35.0f, 20.0f);
    runCycle();
    wake();  // hostSeen == 0 from the previous cycle (no host)

    setup();

    CHECK(fake::state().nowMs >= CFG.noHostProbeMs);
    CHECK(fake::state().nowMs <= CFG.noHostProbeMs + 50);
    CHECK(rtcData.hostSeen == 0);
}

TEST(wake_with_remembered_host_waits_for_cdc_reconnect_then_exits_early) {
    powerOn();
    fake::state().cdcReadyAtMs = 0;
    setProbes(2, 35.0f, 20.0f);
    runCycle();
    CHECK(rtcData.hostSeen == 1);

    wake();
    fake::state().busActiveAtMs = 0;       // cable still on a host (IDF>=5 sees SOF at once)
    fake::state().cdcReadyAtMs = 800;      // monitor re-opens the port after 800 ms

    setup();

    // Must honour the reconnect budget past the 300 ms probe cut, on both cores.
    CHECK(fake::state().nowMs >= 800);
    CHECK(fake::state().nowMs < 900);
    CHECK(rtcData.hostSeen == 1);
}

TEST(wake_with_remembered_host_but_cable_removed_stops_early_when_bus_detect_exists) {
    powerOn();
    fake::state().cdcReadyAtMs = 0;
    setProbes(2, 35.0f, 20.0f);
    runCycle();

    wake();
    fake::state().busActiveAtMs = fake::NEVER_MS;   // cable unplugged: no SOF ...
    fake::state().cdcReadyAtMs  = fake::NEVER_MS;   // ... and no monitor

    setup();

    if (kHasBusDetect) {
        CHECK(fake::state().nowMs <= CFG.noHostProbeMs + 50);   // SOF absent -> give up early
    } else {
        CHECK(fake::state().nowMs >= CFG.hostSeenWaitMs);       // core 2.x cannot tell: full budget once
    }
    CHECK(rtcData.hostSeen == 0);   // next wake is a short probe again
}

// ───────────────────────── sensors ─────────────────────────

TEST(single_probe_is_sensor_error_and_is_not_cached) {
    powerOn();
    setProbes(1, 35.0f, 20.0f);
    setStoreVoltage(3.0f);

    runCycle();

    CHECK(contains(lastCsvRow()[COL_STATE], "SENSOR_ERR"));
    CHECK(gateHighCount() == 0);
    CHECK(rtcData.sensorCount == 0);   // rediscover on the next wake
}

TEST(second_probe_plugged_in_later_is_discovered_and_engine_recovers) {
    powerOn();
    setProbes(1, 35.0f, 20.0f);
    setStoreVoltage(3.0f);
    runCycle();

    wake();
    setProbes(2, 35.0f, 20.0f);
    runCycle();

    CHECK(fake::state().beginCalls == 1);           // rediscovery happened
    CHECK(rtcData.sensorCount == 2);
    CHECK(contains(lastCsvRow()[COL_STATE], "DEMON_ACT"));
    CHECK(gateHighCount() == static_cast<int>(demon::SOS_SYMBOL_COUNT));
}

TEST(cached_probes_skip_bus_discovery_on_later_wakes) {
    powerOn();
    setProbes(2, 35.0f, 20.0f);
    setStoreVoltage(1.5f);
    runCycle();
    CHECK(fake::state().beginCalls == 1);

    wake();
    runCycle();

    CHECK(fake::state().beginCalls == 0);
    CHECK(fake::state().requestCalls == 1);
}

TEST(read_failure_after_valid_cycle_blocks_actuation_and_forces_rediscovery) {
    powerOn();
    setProbes(2, 35.0f, 20.0f);
    setStoreVoltage(3.0f);
    runCycle();
    CHECK(contains(lastCsvRow()[COL_STATE], "DEMON_ACT"));

    wake();
    fake::state().readFails = true;   // probes unplugged; RTC still holds a 15 C difference
    runCycle();

    CHECK(contains(lastCsvRow()[COL_STATE], "SENSOR_ERR"));
    CHECK(gateHighCount() == 0);
    CHECK(rtcData.sensorCount == 0);
}

// ───────────────────────── demon + sleep ─────────────────────────

TEST(flash_then_fast_sleep_on_large_delta_t) {
    powerOn();
    setProbes(2, 35.0f, 20.0f);
    setStoreVoltage(3.0f);

    runCycle();

    const auto row = lastCsvRow();
    CHECK(row.size() == COL_COUNT);
    CHECK(contains(row[COL_STATE], "DEMON_ACT"));
    CHECK(fake::state().sleepUs == CFG.sleepFastUs);
    CHECK(fake::state().deepSleepCalls == 1);
    CHECK(rtcData.sosFlashCount == 1);
}

TEST(charging_below_threshold_does_not_flash) {
    powerOn();
    setProbes(2, 35.0f, 20.0f);
    setStoreVoltage(2.0f);

    runCycle();

    CHECK(contains(lastCsvRow()[COL_STATE], "CHARGING"));
    CHECK(gateHighCount() == 0);
    CHECK(fake::state().sleepUs == CFG.sleepGuardUs);   // no history yet -> static rule
}

// ───────────────────────── energy accounting ─────────────────────────

TEST(first_flash_row_already_carries_this_cycles_active_cost) {
    powerOn();
    fake::state().cdcReadyAtMs = 0;
    setProbes(2, 35.0f, 20.0f);
    setStoreVoltage(3.0f);

    runCycle();

    const auto row = lastCsvRow();
    const double wActive = std::stod(row[COL_W_ACTIVE]);
    const long awakeMs = std::stol(row[COL_AWAKE_MS]);
    // 3 s grace + SOS (2.8 s) must be visible in this very row, not deferred.
    CHECK(awakeMs >= 5800);
    CHECK(wActive > 300.0);
    CHECK(std::fabs(wActive - demon::activeCost_mJ(static_cast<uint32_t>(awakeMs), CFG)) < 1.0);
    // W_net_total = W_ext - W_landauer - W_active, all for this cycle.
    const double wNetTotal = std::stod(row[COL_W_NET_TOTAL]);
    const double wNet = std::stod(row[COL_W_NET]);
    CHECK(std::fabs((wNet - wActive) - wNetTotal) < 0.05);
}

TEST(active_cost_accumulates_across_wakes) {
    powerOn();
    setProbes(2, 35.0f, 20.0f);
    setStoreVoltage(1.5f);
    runCycle();
    const float afterFirst = rtcData.activeCost_mJ;
    CHECK(afterFirst > 0.0f);

    wake();
    runCycle();

    CHECK(rtcData.activeCost_mJ > afterFirst);
}

}  // namespace

int main() {
    std::printf("\n%d checks, %d failures (IDF %d.x fakes)\n", g_checks, g_failures, STUB_IDF_MAJOR);
    return g_failures == 0 ? 0 : 1;
}
