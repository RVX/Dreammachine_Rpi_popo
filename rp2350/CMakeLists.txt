cmake_minimum_required(VERSION 3.13)

include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(dreammachine_rp2350 C CXX ASM)

pico_sdk_init()

add_executable(dreammachine_rp2350
    main.c
)

target_link_libraries(dreammachine_rp2350
    hardware_spi
    pico_stdlib
)

pico_enable_stdio_usb(dreammachine_rp2350 1)
pico_enable_stdio_uart(dreammachine_rp2350 0)
pico_add_extra_outputs(dreammachine_rp2350)