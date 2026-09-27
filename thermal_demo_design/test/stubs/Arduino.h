// Minimal Arduino / ESP32 API stub for host-side syntax checking of the sketch.
// Only the symbols used by maxwell_demon_harvester_esp32c3.ino are declared.
#pragma once

#include <cstdint>
#include <cstddef>
#include <math.h>

#define HIGH 1
#define LOW 0
#define OUTPUT 1
#define INPUT_PULLUP 5
#define INPUT_PULLDOWN 9
#define ADC_11db 3
#define RTC_DATA_ATTR
#define F(x) (x)

inline void pinMode(int, int) {}
inline void digitalWrite(int, int) {}
inline int analogRead(int) { return 0; }
inline void analogSetAttenuation(int) {}
inline void analogReadResolution(int) {}
inline void delay(uint32_t) {}
inline uint32_t millis() { return 0; }
inline bool setCpuFrequencyMhz(uint32_t) { return true; }

struct SerialStub {
    void begin(unsigned long) {}
    void flush() {}
    void println() {}
    template <class T> void print(const T&) {}
    template <class T> void print(const T&, int) {}
    template <class T> void println(const T&) {}
    template <class T> void println(const T&, int) {}
};
inline SerialStub Serial;
