// Stateful fake of ESP-IDF esp_sleep.h (see fake::State in Arduino.h).
#pragma once
#include <cstdint>
#include "Arduino.h"

inline int esp_sleep_enable_timer_wakeup(uint64_t us) { fake::state().sleepUs = us; return 0; }
inline void esp_deep_sleep_start() { fake::state().deepSleepCalls++; }
