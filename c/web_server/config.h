/**
 * Configuration for Waveshare RP2350-POE-ETH-8DI-8RO
 * Relay Control Web Server
 */

#ifndef _CONFIG_H_
#define _CONFIG_H_

#include <stdint.h>

// Network Configuration
#define NET_MAC         {0x00, 0x08, 0xDC, 0x12, 0x34, 0x56}
#define NET_IP          {192, 168, 1, 100}
#define NET_SUBNET      {255, 255, 255, 0}
#define NET_GATEWAY     {192, 168, 1, 1}
#define NET_DNS         {8, 8, 8, 8}

// HTTP Server Configuration
#define HTTP_SOCKET     0
#define HTTP_PORT       80
#define MAX_HTTP_BUF    2048

// Relay GPIO Pins (17-24)
#define RELAY_CH1       17
#define RELAY_CH2       18
#define RELAY_CH3       19
#define RELAY_CH4       20
#define RELAY_CH5       21
#define RELAY_CH6       22
#define RELAY_CH7       23
#define RELAY_CH8       24

#define RELAY_COUNT     8

// Global relay state array
extern uint8_t g_relay_states[RELAY_COUNT];

#endif /* _CONFIG_H_ */
