#include "driver/gpio.h"
#include "driver/ledc.h"
#include "driver/uart.h"
#include "esp_check.h"
#include "esp_err.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <ctype.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LIGHT_PIN_COUNT            4
#define LIGHT_CONTROL_UART         UART_NUM_0
#define LIGHT_PWM_MODE             LEDC_LOW_SPEED_MODE
#define LIGHT_PWM_TIMER            LEDC_TIMER_0
#define LIGHT_PWM_RESOLUTION       LEDC_TIMER_8_BIT
#define LIGHT_PWM_FREQUENCY_HZ     5000
#define SERIAL_TASK_STACK_SIZE     4096
#define SERIAL_TASK_PRIORITY       5
#define SERIAL_READ_TIMEOUT_MS     100
#define CHARIS_BUFFER_SIZE         64
#define DEFAULT_BRIGHTNESS_PERCENT 75

// ELEGOO's USB-C ESP-WROOM-32 board is a classic ESP32 dev board.
// These GPIOs are exposed, output-capable, and avoid the flash/UART pins.
static const gpio_num_t s_pins[LIGHT_PIN_COUNT] = {
    GPIO_NUM_26,
    GPIO_NUM_25,
    GPIO_NUM_33,
    GPIO_NUM_32,
};
static const ledc_channel_t s_ledc_channels[LIGHT_PIN_COUNT] = {
    LEDC_CHANNEL_0,
    LEDC_CHANNEL_1,
    LEDC_CHANNEL_2,
    LEDC_CHANNEL_3,
};

static const int s_pin_numbers[LIGHT_PIN_COUNT] = {26, 25, 33, 32};
static const char *TAG = "mbot_renderer";
static uint8_t s_current_mask = 0;
static uint8_t s_brightness_percent = DEFAULT_BRIGHTNESS_PERCENT;

static uint32_t brightness_percent_to_duty(uint8_t percent)
{
    uint32_t max_duty = (1U << LIGHT_PWM_RESOLUTION) - 1U;
    return (max_duty * percent) / 100U;
}

static void set_pin_mask(uint8_t mask)
{
    uint32_t on_duty = brightness_percent_to_duty(s_brightness_percent);
    for (size_t i = 0; i < LIGHT_PIN_COUNT; i++) {
        uint32_t duty = ((mask >> i) & 0x1U) ? on_duty : 0U;
        ledc_set_duty(LIGHT_PWM_MODE, s_ledc_channels[i], duty);
        ledc_update_duty(LIGHT_PWM_MODE, s_ledc_channels[i]);
    }
    s_current_mask = mask;
}

static void stop_all_pins(void)
{
    set_pin_mask(0);
}

static esp_err_t init_pins(void)
{
    const ledc_timer_config_t timer_cfg = {
        .speed_mode = LIGHT_PWM_MODE,
        .duty_resolution = LIGHT_PWM_RESOLUTION,
        .timer_num = LIGHT_PWM_TIMER,
        .freq_hz = LIGHT_PWM_FREQUENCY_HZ,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_RETURN_ON_ERROR(ledc_timer_config(&timer_cfg), TAG, "pwm timer init failed");

    for (size_t i = 0; i < LIGHT_PIN_COUNT; i++) {
        gpio_reset_pin(s_pins[i]);
        const ledc_channel_config_t channel_cfg = {
            .gpio_num = s_pins[i],
            .speed_mode = LIGHT_PWM_MODE,
            .channel = s_ledc_channels[i],
            .intr_type = LEDC_INTR_DISABLE,
            .timer_sel = LIGHT_PWM_TIMER,
            .duty = 0,
            .hpoint = 0,
            .sleep_mode = LEDC_SLEEP_MODE_NO_ALIVE_NO_PD,
        };
        ESP_RETURN_ON_ERROR(ledc_channel_config(&channel_cfg), TAG, "pwm channel init failed");
    }

    return ESP_OK;
}

static esp_err_t init_serial_control(void)
{
    const uart_config_t uart_cfg = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .rx_flow_ctrl_thresh = 0,
        .source_clk = UART_SCLK_DEFAULT,
    };

    ESP_RETURN_ON_ERROR(uart_param_config(LIGHT_CONTROL_UART, &uart_cfg),
                        TAG,
                        "serial config failed");
    ESP_RETURN_ON_ERROR(uart_set_pin(LIGHT_CONTROL_UART,
                                     UART_PIN_NO_CHANGE,
                                     UART_PIN_NO_CHANGE,
                                     UART_PIN_NO_CHANGE,
                                     UART_PIN_NO_CHANGE),
                        TAG,
                        "serial pin config failed");
    ESP_RETURN_ON_ERROR(uart_driver_install(LIGHT_CONTROL_UART, 256, 0, 0, NULL, 0),
                        TAG,
                        "serial driver install failed");
    ESP_RETURN_ON_ERROR(uart_flush_input(LIGHT_CONTROL_UART), TAG, "serial flush failed");

    return ESP_OK;
}

static void write_reply(const char *reply)
{
    uart_write_bytes(LIGHT_CONTROL_UART, reply, strlen(reply));
}

static void write_info(void)
{
    char buffer[96];
    int written = snprintf(buffer,
                           sizeof(buffer),
                           "OK PINS %d %d %d %d BRIGHTNESS %u\n",
                           s_pin_numbers[0],
                           s_pin_numbers[1],
                           s_pin_numbers[2],
                           s_pin_numbers[3],
                           s_brightness_percent);
    if (written > 0) {
        uart_write_bytes(LIGHT_CONTROL_UART, buffer, (size_t)written);
    }
}

static char *trim_in_place(char *text)
{
    while (*text != '\0' && isspace((unsigned char)*text)) {
        text++;
    }

    size_t len = strlen(text);
    while (len > 0 && isspace((unsigned char)text[len - 1])) {
        text[len - 1] = '\0';
        len--;
    }

    return text;
}

static bool parse_mask_value(const char *text, uint8_t *mask_out)
{
    char *end = NULL;
    long value = strtol(text, &end, 0);
    if (end == text || *end != '\0' || value < 0 || value > 0x0F) {
        return false;
    }

    *mask_out = (uint8_t)value;
    return true;
}

static bool parse_brightness_percent(const char *text, uint8_t *brightness_out)
{
    char *end = NULL;
    long value = strtol(text, &end, 0);
    if (end == text || *end != '\0' || value < 0 || value > 100) {
        return false;
    }

    *brightness_out = (uint8_t)value;
    return true;
}

static void process_command(char *line)
{
    uint8_t mask = 0;
    uint8_t brightness = 0;
    char *command = trim_in_place(line);

    if (*command == '\0') {
        return;
    }

    if (strcmp(command, "PING") == 0 || strcmp(command, "INFO") == 0) {
        write_info();
        return;
    }

    if (strcmp(command, "OFF") == 0 || strcmp(command, "RESET") == 0) {
        stop_all_pins();
        return;
    }

    if (strcmp(command, "BRIGHTNESS") == 0) {
        write_info();
        return;
    }

    if (strncmp(command, "MASK ", 5) == 0 && parse_mask_value(command + 5, &mask)) {
        set_pin_mask(mask);
        return;
    }

    if (command[0] == 'M' && command[1] != '\0' && parse_mask_value(command + 1, &mask)) {
        set_pin_mask(mask);
        return;
    }

    if (strncmp(command, "BRIGHTNESS ", 11) == 0
        && parse_brightness_percent(command + 11, &brightness)) {
        s_brightness_percent = brightness;
        set_pin_mask(s_current_mask);
        write_info();
        return;
    }

    write_reply("ERR\n");
}

static void serial_renderer_task(void *arg)
{
    uint8_t byte = 0;
    size_t length = 0;
    bool discarding_line = false;
    char buffer[CHARIS_BUFFER_SIZE];
    (void)arg;

    write_info();
    ESP_LOGI(TAG,
             "Serial renderer ready on GPIO %d, %d, %d, %d",
             s_pin_numbers[0],
             s_pin_numbers[1],
             s_pin_numbers[2],
             s_pin_numbers[3]);

    while (true) {
        int read_len = uart_read_bytes(LIGHT_CONTROL_UART,
                                       &byte,
                                       sizeof(byte),
                                       pdMS_TO_TICKS(SERIAL_READ_TIMEOUT_MS));
        if (read_len <= 0) {
            continue;
        }

        if (byte == '\n' || byte == '\r') {
            if (discarding_line) {
                discarding_line = false;
                length = 0;
                continue;
            }

            if (length == 0) {
                continue;
            }

            buffer[length] = '\0';
            process_command(buffer);
            length = 0;
            continue;
        }

        if (discarding_line) {
            continue;
        }

        if (length + 1 >= sizeof(buffer)) {
            length = 0;
            discarding_line = true;
            write_reply("ERR\n");
            continue;
        }

        buffer[length++] = (char)byte;
    }
}

void app_main(void)
{
    ESP_LOGI(TAG,
             "Preparing serial-rendered light output on GPIO %d, %d, %d, %d",
             s_pin_numbers[0],
             s_pin_numbers[1],
             s_pin_numbers[2],
             s_pin_numbers[3]);

    ESP_ERROR_CHECK(init_pins());
    ESP_ERROR_CHECK(init_serial_control());
    stop_all_pins();

    xTaskCreate(serial_renderer_task,
                "serial_renderer",
                SERIAL_TASK_STACK_SIZE,
                NULL,
                SERIAL_TASK_PRIORITY,
                NULL);

    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
