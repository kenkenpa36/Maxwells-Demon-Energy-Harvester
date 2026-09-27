// Stateful fake of the DallasTemperature library (see fake::State in Arduino.h).
#pragma once
#include <cstdint>
#include "Arduino.h"
#include "OneWire.h"

#define DEVICE_DISCONNECTED_C -127

typedef uint8_t DeviceAddress[8];

class DallasTemperature {
public:
    explicit DallasTemperature(OneWire*) {}
    void begin() { fake::state().beginCalls++; }
    uint8_t getDeviceCount() { return fake::state().deviceCount; }
    // Fake ROM address: byte 0 = probe number (1-based), rest zero.
    bool getAddress(uint8_t* addr, uint8_t index) {
        if (index >= fake::state().deviceCount) return false;
        for (int i = 0; i < 8; i++) addr[i] = 0;
        addr[0] = static_cast<uint8_t>(index + 1);
        return true;
    }
    void setResolution(uint8_t) {}
    void setWaitForConversion(bool) {}
    void requestTemperatures() { fake::state().requestCalls++; }
    float getTempC(const uint8_t* addr) {
        const fake::State& s = fake::state();
        if (s.readFails || addr[0] == 0 || addr[0] > s.deviceCount) return DEVICE_DISCONNECTED_C;
        return s.temps[addr[0] - 1];
    }
    float getTempCByIndex(uint8_t index) {
        uint8_t addr[8];
        return getAddress(addr, index) ? getTempC(addr) : DEVICE_DISCONNECTED_C;
    }
};
