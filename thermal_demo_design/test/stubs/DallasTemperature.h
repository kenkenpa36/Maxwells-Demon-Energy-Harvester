// Stub of the DallasTemperature library for host-side syntax checking.
#pragma once
#include <cstdint>
#include "OneWire.h"

#define DEVICE_DISCONNECTED_C -127

typedef uint8_t DeviceAddress[8];

class DallasTemperature {
public:
    explicit DallasTemperature(OneWire*) {}
    void begin() {}
    uint8_t getDeviceCount() { return 0; }
    bool getAddress(uint8_t*, uint8_t) { return false; }
    void setResolution(uint8_t) {}
    void setWaitForConversion(bool) {}
    void requestTemperatures() {}
    float getTempC(const uint8_t*) { return DEVICE_DISCONNECTED_C; }
    float getTempCByIndex(uint8_t) { return DEVICE_DISCONNECTED_C; }
};
