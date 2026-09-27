// Stub of the DallasTemperature library for host-side syntax checking.
#pragma once
#include <cstdint>
#include "OneWire.h"

#define DEVICE_DISCONNECTED_C -127

class DallasTemperature {
public:
    explicit DallasTemperature(OneWire*) {}
    void begin() {}
    uint8_t getDeviceCount() { return 0; }
    void setResolution(uint8_t) {}
    void setWaitForConversion(bool) {}
    void requestTemperatures() {}
    float getTempCByIndex(uint8_t) { return DEVICE_DISCONNECTED_C; }
};
