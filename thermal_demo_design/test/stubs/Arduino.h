// Stateful fake of the Arduino / ESP32 API used by maxwell_demon_harvester_esp32c3_v2.ino.
// Serves two purposes on the host:
//   - syntax checking the sketch (run_tests.sh --syntax)
//   - driving setup()/loop() from test_sketch.cpp with controllable time, USB
//     state, ADC value and DS18B20 behaviour (see fake::State).
#pragma once

#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <math.h>
#include <string>
#include <utility>
#include <vector>

#define HIGH 1
#define LOW 0
#define OUTPUT 1
#define INPUT_PULLUP 5
#define INPUT_PULLDOWN 9
#define ADC_11db 3
#define RTC_DATA_ATTR
#define F(x) (x)

namespace fake {

constexpr uint32_t NEVER_MS = 0xFFFFFFFFu;

struct State {
    // --- time ---
    uint32_t nowMs = 0;                  // millis(); advanced only by delay()
    // --- USB ---
    uint32_t cdcReadyAtMs  = NEVER_MS;   // Serial becomes true from this time (host app opened the port)
    uint32_t busActiveAtMs = NEVER_MS;   // usb_serial_jtag_is_connected() true from this time (SOF on bus)
    // --- MCU ---
    int      resetReason = 1;            // ESP_RST_POWERON (see esp_system.h)
    uint32_t cpuMhz = 0;
    int      adcRaw = 0;
    std::string serialOut;
    std::vector<std::pair<int, int>> pinWrites;  // (pin, level)
    uint64_t sleepUs = 0;
    int      deepSleepCalls = 0;
    // --- DS18B20 ---
    uint8_t  deviceCount = 0;            // probes present on the bus
    float    temps[2] = {0.0f, 0.0f};    // temperature of probe 1 / probe 2
    bool     readFails = false;          // every scratchpad read returns DEVICE_DISCONNECTED_C
    int      beginCalls = 0;
    int      requestCalls = 0;
};

inline State& state() {
    static State s;
    return s;
}

inline void reset() { state() = State(); }

}  // namespace fake

inline void pinMode(int, int) {}
inline void digitalWrite(int pin, int level) { fake::state().pinWrites.emplace_back(pin, level); }
inline int analogRead(int) { return fake::state().adcRaw; }
inline void analogSetAttenuation(int) {}
inline void analogReadResolution(int) {}
inline void delay(uint32_t ms) { fake::state().nowMs += ms; }
inline uint32_t millis() { return fake::state().nowMs; }
inline bool setCpuFrequencyMhz(uint32_t mhz) { fake::state().cpuMhz = mhz; return true; }

// HWCDC-like serial. operator bool() reports whether the host has the CDC port open.
struct SerialStub {
    void begin(unsigned long) {}
    void flush() {}
    explicit operator bool() const { return fake::state().nowMs >= fake::state().cdcReadyAtMs; }

    void print(const char* s) { out() += s; }
    void print(char c) { out() += c; }
    void print(int v) { out() += std::to_string(v); }
    void print(unsigned v) { out() += std::to_string(v); }
    void print(long v) { out() += std::to_string(v); }
    void print(unsigned long v) { out() += std::to_string(v); }
    void print(long long v) { out() += std::to_string(v); }
    void print(unsigned long long v) { out() += std::to_string(v); }
    void print(double v, int digits = 2) {
        char buf[48];
        std::snprintf(buf, sizeof buf, "%.*f", digits, v);
        out() += buf;
    }
    void println() { out() += '\n'; }
    void println(double v, int digits) { print(v, digits); println(); }
    template <class T> void println(const T& v) { print(v); println(); }

private:
    static std::string& out() { return fake::state().serialOut; }
};
inline SerialStub Serial;
