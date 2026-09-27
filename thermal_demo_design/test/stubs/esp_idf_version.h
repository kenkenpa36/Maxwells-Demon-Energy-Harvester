// Stub of ESP-IDF esp_idf_version.h for host-side syntax checking.
// Compile with -DSTUB_IDF_MAJOR=4 to exercise the arduino-esp32 2.x (IDF 4.4)
// code path, or leave the default (5) for arduino-esp32 3.x (IDF 5.x).
#pragma once

#ifndef STUB_IDF_MAJOR
#define STUB_IDF_MAJOR 5
#endif

#define ESP_IDF_VERSION_VAL(major, minor, patch) ((major << 16) | (minor << 8) | (patch))
#define ESP_IDF_VERSION ESP_IDF_VERSION_VAL(STUB_IDF_MAJOR, 0, 0)
