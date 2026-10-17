# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

find_package(GTest REQUIRED)
include(GoogleTest)

juce_add_console_app(a3-desk-tests PRODUCT_NAME "a3-desk-tests")
target_sources(a3-desk-tests PRIVATE
    TestRunner.cpp
    DeskInboxTests.cpp
    DeskLayoutTests.cpp
    EncoderTurnsTests.cpp
    DeskOscTests.cpp
    DeskStateTests.cpp
    DeskUiTests.cpp
    DeskWireTests.cpp
    DisplayPictureTests.cpp
    GuardTests.cpp
    LedScaleTests.cpp
    MeterBallisticsTests.cpp
    SharedTests.cpp
    ${A3DESK_SOURCES_ABS})
target_include_directories(a3-desk-tests PRIVATE "${PROJECT_SOURCE_DIR}/Source" "${CMAKE_CURRENT_SOURCE_DIR}")
target_compile_definitions(a3-desk-tests PRIVATE ${A3DESK_DEFINITIONS}
    A3DESK_FIXTURES="${PROJECT_SOURCE_DIR}/../software/tests/fixtures")
target_compile_options(a3-desk-tests PRIVATE -Werror=switch)
target_link_libraries(a3-desk-tests
    PRIVATE juce::juce_gui_basics juce::juce_osc juce::juce_cryptography GTest::gtest
    PUBLIC juce::juce_recommended_config_flags juce::juce_recommended_warning_flags)
# PRE_TEST: the list is read when ctest runs, under xvfb-run, not at build time.
gtest_discover_tests(a3-desk-tests DISCOVERY_MODE PRE_TEST)
