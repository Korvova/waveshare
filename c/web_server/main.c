/**
 * HTTP Web Server for Relay Control
 * Waveshare RP2350-POE-ETH-8DI-8RO
 *
 * Based on Waveshare MQTT example
 * Adapted for HTTP control of 8 relays
 */

#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/gpio.h"
#include "hardware/spi.h"

// WIZnet W5500 includes (from Waveshare demo)
#include "port_common.h"
#include "ethchip_spi.h"
#include "ethchip_conf.h"
#include "socket.h"

// Project includes
#include "config.h"
#include "web_pages.h"

// Relay state array
uint8_t g_relay_states[RELAY_COUNT] = {0};

/**
 * Initialize relay GPIOs
 */
void relay_init(void) {
    const uint8_t relay_pins[] = {RELAY_CH1, RELAY_CH2, RELAY_CH3, RELAY_CH4,
                                   RELAY_CH5, RELAY_CH6, RELAY_CH7, RELAY_CH8};

    for (int i = 0; i < RELAY_COUNT; i++) {
        gpio_init(relay_pins[i]);
        gpio_set_dir(relay_pins[i], GPIO_OUT);
        gpio_put(relay_pins[i], 0);  // Initially OFF
        g_relay_states[i] = 0;
    }

    printf("Relays initialized (GPIO 17-24)\n");
}

/**
 * Set relay state
 */
void set_relay(uint8_t relay_num, uint8_t state) {
    if (relay_num >= 1 && relay_num <= RELAY_COUNT) {
        const uint8_t relay_pins[] = {RELAY_CH1, RELAY_CH2, RELAY_CH3, RELAY_CH4,
                                       RELAY_CH5, RELAY_CH6, RELAY_CH7, RELAY_CH8};
        gpio_put(relay_pins[relay_num - 1], state ? 1 : 0);
        g_relay_states[relay_num - 1] = state ? 1 : 0;
        printf("Relay %d: %s\n", relay_num, state ? "ON" : "OFF");
    }
}

/**
 * Get relay states as JSON
 */
void get_relays_json(char *buffer, size_t bufsize) {
    snprintf(buffer, bufsize,
        "{\"relay_1\":{\"state\":%d},\"relay_2\":{\"state\":%d},"
        "\"relay_3\":{\"state\":%d},\"relay_4\":{\"state\":%d},"
        "\"relay_5\":{\"state\":%d},\"relay_6\":{\"state\":%d},"
        "\"relay_7\":{\"state\":%d},\"relay_8\":{\"state\":%d}}",
        g_relay_states[0], g_relay_states[1], g_relay_states[2], g_relay_states[3],
        g_relay_states[4], g_relay_states[5], g_relay_states[6], g_relay_states[7]);
}

/**
 * Simple HTTP response helper
 */
void send_http_response(uint8_t sock, const char *status, const char *content_type, const char *body) {
    char header[256];
    snprintf(header, sizeof(header),
             "HTTP/1.1 %s\r\n"
             "Content-Type: %s\r\n"
             "Content-Length: %d\r\n"
             "Connection: close\r\n\r\n",
             status, content_type, strlen(body));

    send(sock, (uint8_t*)header, strlen(header));
    send(sock, (uint8_t*)body, strlen(body));
}

/**
 * Process HTTP request
 */
void process_http_request(uint8_t sock, char *request, uint16_t len) {
    char response_buf[512];

    // Parse request line
    char method[16] = {0};
    char uri[128] = {0};
    sscanf(request, "%s %s", method, uri);

    printf("Request: %s %s\n", method, uri);

    // Route handling
    if (strcmp(method, "GET") == 0) {
        if (strcmp(uri, "/") == 0 || strcmp(uri, "/index.html") == 0) {
            // Serve main HTML page
            send_http_response(sock, "200 OK", "text/html", HTML_PAGE);
        }
        else if (strcmp(uri, "/api/relays") == 0) {
            // Return relay states as JSON
            get_relays_json(response_buf, sizeof(response_buf));
            send_http_response(sock, "200 OK", "application/json", response_buf);
        }
        else {
            send_http_response(sock, "404 Not Found", "text/plain", "Not Found");
        }
    }
    else if (strcmp(method, "POST") == 0) {
        if (strncmp(uri, "/api/relay/", 11) == 0) {
            // Control individual relay: /api/relay/1
            int relay_num = uri[11] - '0';

            // Parse JSON body {"state":1} or {"state":0}
            char *body = strstr(request, "\r\n\r\n");
            if (body) {
                body += 4;  // Skip \r\n\r\n
                int state = 0;
                if (strstr(body, "\"state\":1") || strstr(body, "\"state\": 1")) {
                    state = 1;
                } else if (strstr(body, "\"state\":0") || strstr(body, "\"state\": 0")) {
                    state = 0;
                }
                set_relay(relay_num, state);
                send_http_response(sock, "200 OK", "application/json", "{\"success\":true}");
            }
        }
        else if (strcmp(uri, "/api/relays/all/on") == 0) {
            // Turn all relays ON
            for (int i = 1; i <= RELAY_COUNT; i++) {
                set_relay(i, 1);
            }
            send_http_response(sock, "200 OK", "application/json", "{\"success\":true}");
        }
        else if (strcmp(uri, "/api/relays/all/off") == 0) {
            // Turn all relays OFF
            for (int i = 1; i <= RELAY_COUNT; i++) {
                set_relay(i, 0);
            }
            send_http_response(sock, "200 OK", "application/json", "{\"success\":true}");
        }
        else {
            send_http_response(sock, "404 Not Found", "text/plain", "Not Found");
        }
    }
}

/**
 * HTTP server loop
 */
void http_server_run(uint8_t sock) {
    uint8_t status = getSn_SR(sock);
    uint16_t size = 0;
    uint8_t buffer[MAX_HTTP_BUF];

    switch (status) {
        case SOCK_ESTABLISHED:
            // Check if data is available
            if ((size = getSn_RX_RSR(sock)) > 0) {
                if (size > MAX_HTTP_BUF) size = MAX_HTTP_BUF;

                // Receive HTTP request
                recv(sock, buffer, size);
                buffer[size] = '\0';

                // Process request
                process_http_request(sock, (char*)buffer, size);

                // Close connection
                disconnect(sock);
            }
            break;

        case SOCK_CLOSE_WAIT:
            disconnect(sock);
            break;

        case SOCK_INIT:
            listen(sock);
            printf("HTTP Server listening on port %d\n", HTTP_PORT);
            break;

        case SOCK_CLOSED:
            socket(sock, Sn_MR_TCP, HTTP_PORT, 0);
            break;

        default:
            break;
    }
}

/**
 * Main entry point
 */
int main() {
    // 1. System initialization
    stdio_init_all();
    printf("\n========================================\n");
    printf("Waveshare RP2350-POE-ETH-8DI-8RO\n");
    printf("HTTP Relay Control Server\n");
    printf("========================================\n\n");

    // Wait for USB serial
    sleep_ms(2000);

    // 2. Initialize W5500 Ethernet
    printf("Initializing W5500 Ethernet...\n");
    ethchip_spi_initialize();
    ethchip_cris_initialize();
    ethchip_reset();
    ethchip_initialize();
    ethchip_check();
    printf("W5500 initialized successfully\n");

    // 3. Configure network
    uint8_t mac[] = NET_MAC;
    uint8_t ip[] = NET_IP;
    uint8_t subnet[] = NET_SUBNET;
    uint8_t gateway[] = NET_GATEWAY;
    uint8_t dns[] = NET_DNS;

    NetInfo net_info = {
        .mac = {mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]},
        .ip = {ip[0], ip[1], ip[2], ip[3]},
        .sn = {subnet[0], subnet[1], subnet[2], subnet[3]},
        .gw = {gateway[0], gateway[1], gateway[2], gateway[3]},
        .dns = {dns[0], dns[1], dns[2], dns[3]},
        .dhcp = NETINFO_STATIC
    };

    network_initialize(net_info);
    print_network_information(net_info);

    // 4. Initialize relays
    printf("\nInitializing relays...\n");
    relay_init();

    // 5. Initialize HTTP server socket
    printf("\nStarting HTTP server...\n");
    socket(HTTP_SOCKET, Sn_MR_TCP, HTTP_PORT, 0);

    printf("\n========================================\n");
    printf("Server ready!\n");
    printf("Open browser: http://%d.%d.%d.%d\n", ip[0], ip[1], ip[2], ip[3]);
    printf("========================================\n\n");

    // 6. Main server loop
    while (1) {
        http_server_run(HTTP_SOCKET);
    }

    return 0;
}
