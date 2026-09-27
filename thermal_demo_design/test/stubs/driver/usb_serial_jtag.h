// Stateful fake of ESP-IDF driver/usb_serial_jtag.h (IDF >= 5 only; see fake::State in Arduino.h).
#pragma once
#include "../Arduino.h"

inline bool usb_serial_jtag_is_connected() {
    return fake::state().nowMs >= fake::state().busActiveAtMs;
}
