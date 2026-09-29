#include <stdio.h>

#include "hardware/pwm.h"
#include "hardware/spi.h"
#include "hardware/timer.h"
#include "pico/stdlib.h"

enum {
    SPI_RX_PIN = 20,
    SPI_CSN_PIN = 17,
    SPI_SCK_PIN = 18,
    SPI_TX_PIN = 19,
    AMP_SDZ_PIN = 28,
    AMP_FAULTZ_PIN = 29,
    AMP_MUTE_PIN = 30,
};

static const uint MOSFET_PINS[] = {33, 34, 35, 36, 37, 38};

// Wrap 255 gives clean 0-100% steps; ~125 MHz / (255+1) / 4 = ~122 kHz.
static const uint PWM_WRAP = 255;
static const uint PWM_CLKDIV = 4;

// Non-blocking fade state per channel
static volatile int fade_brightness[6] = {0};
static volatile int fade_target[6] = {0};
static volatile int fade_step[6] = {0};  // +1 or -1, 0 = not fading
static volatile uint32_t fade_last_update[6] = {0};
static const uint32_t FADE_INTERVAL_MS = 20;  // 20ms per step = ~1s for full 0-255

// Initialize PWM on a pin and set brightness
static void pwm_set(size_t index, uint8_t percent) {
    if (index >= count_of(MOSFET_PINS)) return;
    if (percent > 100) percent = 100;
    uint pin = MOSFET_PINS[index];
    uint slice = pwm_gpio_to_slice_num(pin);
    gpio_set_function(pin, GPIO_FUNC_PWM);
    pwm_set_wrap(slice, PWM_WRAP);
    pwm_set_clkdiv(slice, PWM_CLKDIV);
    pwm_set_enabled(slice, true);
    pwm_set_gpio_level(pin, (percent * (PWM_WRAP + 1)) / 100);
}

// Start a fade: direction = +1 for in, -1 for out
static void fade_start(size_t index, int direction) {
    if (index >= count_of(MOSFET_PINS)) return;
    fade_target[index] = (direction > 0) ? 255 : 0;
    fade_step[index] = direction;
    fade_last_update[index] = time_us_32() / 1000;
}

// Call from main loop: updates all active fades
static void fade_update(void) {
    uint32_t now = time_us_32() / 1000;
    for (size_t i = 0; i < count_of(MOSFET_PINS); ++i) {
        if (fade_step[i] == 0) continue;
        if (now - fade_last_update[i] < FADE_INTERVAL_MS) continue;
        
        fade_last_update[i] = now;
        int next = fade_brightness[i] + fade_step[i] * 5;
        
        // Check if we've reached or passed the target
        if ((fade_step[i] > 0 && next >= fade_target[i]) ||
            (fade_step[i] < 0 && next <= fade_target[i])) {
            next = fade_target[i];
            fade_step[i] = 0;  // fade complete
        }
        
        fade_brightness[i] = next;
        pwm_set(i, (next * 100) / 255);
    }
}

// Stop all fades and set to off
static void fade_stop_all(void) {
    for (size_t i = 0; i < count_of(MOSFET_PINS); ++i) {
        fade_step[i] = 0;
        fade_brightness[i] = 0;
        pwm_set(i, 0);
    }
}

// Switch pin back to plain GPIO output (disables PWM)
static void gpio_mode(size_t index) {
    uint pin = MOSFET_PINS[index];
    uint slice = pwm_gpio_to_slice_num(pin);
    pwm_set_enabled(slice, false);
    gpio_set_function(pin, GPIO_FUNC_SIO);
    gpio_set_dir(pin, GPIO_OUT);
}

static void all_off(void) {
    for (size_t index = 0; index < count_of(MOSFET_PINS); ++index) {
        gpio_mode(index);  // ensure GPIO mode, not PWM
        gpio_put(MOSFET_PINS[index], false);
    }
}

static void pulse(size_t index, uint32_t duration_ms) {
    all_off();
    gpio_mode(index);  // ensure GPIO mode
    gpio_put(MOSFET_PINS[index], true);
    sleep_ms(duration_ms);
    all_off();
}

// Pulse two channels simultaneously (for kick-sync)
static void pulse_dual(size_t ch1, size_t ch2, uint32_t duration_ms) {
    all_off();
    gpio_mode(ch1);
    gpio_mode(ch2);
    gpio_put(MOSFET_PINS[ch1], true);
    gpio_put(MOSFET_PINS[ch2], true);
    sleep_ms(duration_ms);
    all_off();
}

static void chase(void) {
    for (uint round = 0; round < 4; ++round) {
        for (size_t index = 0; index < count_of(MOSFET_PINS); ++index) {
            pulse(index, 180);
            sleep_ms(70);
        }
    }
}

static void bounce(void) {
    for (uint round = 0; round < 3; ++round) {
        for (size_t index = 0; index < count_of(MOSFET_PINS); ++index) {
            pulse(index, 140);
        }
        for (size_t index = count_of(MOSFET_PINS) - 1; index > 0; --index) {
            pulse(index - 1, 140);
        }
    }
}

static void flash_all(void) {
    for (uint flash = 0; flash < 5; ++flash) {
        for (size_t index = 0; index < count_of(MOSFET_PINS); ++index) {
            gpio_put(MOSFET_PINS[index], true);
        }
        sleep_ms(300);
        all_off();
        sleep_ms(300);
    }
}

static void amp_shutdown(void) {
    gpio_put(AMP_MUTE_PIN, true);
    sleep_ms(10);
    gpio_put(AMP_SDZ_PIN, false);
}

static void amp_start_muted(void) {
    gpio_put(AMP_MUTE_PIN, true);
    gpio_put(AMP_SDZ_PIN, true);
    // TPA3118 datasheet wake time from shutdown can exceed a few ms under
    // load/temperature; 20ms was too tight and left FAULTZ transiently low
    // right when amp_unmute() ran its one-shot check, latching a false mute.
    sleep_ms(60);
}

static void amp_unmute(void) {
    // Retry-poll instead of a single check: FAULTZ can still be settling
    // after amp_start_muted(); give it up to 300ms before giving up.
    for (int attempt = 0; attempt < 30; ++attempt) {
        if (gpio_get(AMP_SDZ_PIN) && gpio_get(AMP_FAULTZ_PIN)) {
            gpio_put(AMP_MUTE_PIN, false);
            return;
        }
        sleep_ms(10);
    }
    puts("Amplifier remains muted: shutdown active or FAULTZ still low after 300ms");
}

static void execute_command(uint8_t command) {
    if (command == 0x00) {
        all_off();
        amp_shutdown();
        fade_stop_all();
    } else if (command >= 0x01 && command <= 0x06) {
        pulse(command - 1, 500);
    } else if (command >= 0x51 && command <= 0x56) {
        // Fade IN: 0x50 + channel (1-6)
        fade_start(command - 0x51, 1);
    } else if (command >= 0x61 && command <= 0x66) {
        // Fade OUT: 0x60 + channel (1-6)
        fade_start(command - 0x61, -1);
    } else if (command >= 0x71 && command <= 0x76) {
        // Stop fade and turn off: 0x70 + channel (1-6)
        size_t ch = command - 0x71;
        fade_step[ch] = 0;
        fade_brightness[ch] = 0;
        pwm_set(ch, 0);
    } else if (command == 0x07) {
        // Dual pulse: AMOS1 + AMOS2 together, 100ms (for kick-sync)
        pulse_dual(0, 1, 100);
    } else if (command == 0x08) {
        // Dual ON (non-blocking): AMOS1+AMOS2 held on until 0x09/0x00.
        // Used by the Pi-side FLS stroboscopic protocol for precise
        // frequency/duty-cycle timing (pulse_dual's fixed 100ms blocks).
        fade_step[0] = 0; fade_brightness[0] = 0;
        fade_step[1] = 0; fade_brightness[1] = 0;
        gpio_mode(0);
        gpio_mode(1);
        gpio_put(MOSFET_PINS[0], true);
        gpio_put(MOSFET_PINS[1], true);
    } else if (command == 0x09) {
        // Dual OFF (non-blocking): AMOS1+AMOS2 off
        gpio_put(MOSFET_PINS[0], false);
        gpio_put(MOSFET_PINS[1], false);
    } else if (command == 0x10) {
        chase();
    } else if (command == 0x11) {
        bounce();
    } else if (command == 0x12) {
        flash_all();
    } else if (command == 0x20) {
        amp_shutdown();
    } else if (command == 0x21) {
        amp_start_muted();
    } else if (command == 0x22) {
        amp_unmute();
    } else if (command == 0x23) {
        gpio_put(AMP_MUTE_PIN, true);
    }
}

int main(void) {
    // R79/R81 are removed from the board: these pins have no external bias,
    // so the internal pad pull is the only thing holding a safe level before
    // gpio_set_dir(GPIO_OUT) below takes effect (e.g. boot ROM/BOOTSEL).
    gpio_init(AMP_SDZ_PIN);
    gpio_pull_down(AMP_SDZ_PIN);
    gpio_put(AMP_SDZ_PIN, false);
    gpio_set_dir(AMP_SDZ_PIN, GPIO_OUT);

    gpio_init(AMP_MUTE_PIN);
    gpio_pull_up(AMP_MUTE_PIN);
    gpio_put(AMP_MUTE_PIN, true);
    gpio_set_dir(AMP_MUTE_PIN, GPIO_OUT);

    gpio_init(AMP_FAULTZ_PIN);
    gpio_set_dir(AMP_FAULTZ_PIN, GPIO_IN);
    gpio_pull_up(AMP_FAULTZ_PIN);

    for (size_t index = 0; index < count_of(MOSFET_PINS); ++index) {
        gpio_init(MOSFET_PINS[index]);
        gpio_put(MOSFET_PINS[index], false);
        gpio_set_dir(MOSFET_PINS[index], GPIO_OUT);
    }

    spi_init(spi0, 500 * 1000);
    spi_set_slave(spi0, true);
    spi_set_format(spi0, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
    gpio_set_function(SPI_RX_PIN, GPIO_FUNC_SPI);
    gpio_set_function(SPI_CSN_PIN, GPIO_FUNC_SPI);
    gpio_set_function(SPI_SCK_PIN, GPIO_FUNC_SPI);
    gpio_set_function(SPI_TX_PIN, GPIO_FUNC_SPI);

    stdio_init_all();
    puts("DREAMMACHINE RP2350B SPI controller ready");

    while (true) {
        // Update any active fades (non-blocking)
        fade_update();
        
        if (spi_is_readable(spi0)) {
            uint8_t command;
            spi_read_blocking(spi0, 0, &command, 1);
            printf("SPI command 0x%02x\n", command);
            execute_command(command);
        }

        const int usb_command = getchar_timeout_us(0);
        if (usb_command >= 0 && usb_command <= UINT8_MAX) {
            printf("USB command 0x%02x\n", usb_command);
            execute_command((uint8_t)usb_command);
        }
        tight_loop_contents();
    }
}