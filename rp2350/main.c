#include <stdio.h>

#include "hardware/spi.h"
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

static void all_off(void) {
    for (size_t index = 0; index < count_of(MOSFET_PINS); ++index) {
        gpio_put(MOSFET_PINS[index], false);
    }
}

static void pulse(size_t index, uint32_t duration_ms) {
    all_off();
    gpio_put(MOSFET_PINS[index], true);
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
    sleep_ms(20);
}

static void amp_unmute(void) {
    if (gpio_get(AMP_SDZ_PIN) && gpio_get(AMP_FAULTZ_PIN)) {
        gpio_put(AMP_MUTE_PIN, false);
    } else {
        puts("Amplifier remains muted: shutdown active or FAULTZ is low");
    }
}

static void execute_command(uint8_t command) {
    if (command == 0x00) {
        all_off();
        amp_shutdown();
    } else if (command >= 0x01 && command <= 0x06) {
        pulse(command - 1, 500);
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
    gpio_init(AMP_SDZ_PIN);
    gpio_put(AMP_SDZ_PIN, false);
    gpio_set_dir(AMP_SDZ_PIN, GPIO_OUT);

    gpio_init(AMP_MUTE_PIN);
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
        if (spi_is_readable(spi0)) {
            uint8_t command;
            spi_read_blocking(spi0, 0, &command, 1);
            printf("SPI command 0x%02x\n", command);
            execute_command(command);
        }
        tight_loop_contents();
    }
}