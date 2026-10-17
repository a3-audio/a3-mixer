# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

# A3 Desk: the A3 Mixer on a screen (spec virtual-desk). JUCE 9.0.3 from
# ~/local/juce, as StemDeck and Motion UI build it; no audio.
cmake_minimum_required(VERSION 3.22)
project(A3Desk VERSION 0.1.0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ccache when installed, as StemDeck has it (2026-10-03).
find_program(CCACHE_PROGRAM ccache)
if(CCACHE_PROGRAM)
    set(CCACHE_LAUNCHER "${CMAKE_COMMAND}" -E env "CCACHE_BASEDIR=${CMAKE_SOURCE_DIR}"
        "CCACHE_NOHASHDIR=true" "${CCACHE_PROGRAM}")
    set(CMAKE_C_COMPILER_LAUNCHER ${CCACHE_LAUNCHER})
    set(CMAKE_CXX_COMPILER_LAUNCHER ${CCACHE_LAUNCHER})
endif()

find_package(JUCE 9.0.3 CONFIG REQUIRED)

# Everything but Main.cpp: the app and the tests compile the same list.
set(A3DESK_SOURCES
    Source/DeskControls.cpp
    Source/DeskInbox.cpp
    Source/DeskMeters.cpp
    Source/DeskOsc.cpp
    Source/DeskWire.cpp
    Source/DeskState.cpp
    Source/DisplayPaint.cpp
    Source/DisplayPicture.cpp
    Source/LedScale.cpp
    Source/StartupAsk.cpp
    Source/VuInbox.cpp
    Source/shared/MeterBallistics.cpp
    Source/shared/OscSendGuard.cpp
    Source/shared/OscTruth.cpp
    Source/shared/TruthKeeperLink.cpp)
list(TRANSFORM A3DESK_SOURCES PREPEND "${PROJECT_SOURCE_DIR}/" OUTPUT_VARIABLE A3DESK_SOURCES_ABS)

set(A3DESK_DEFINITIONS JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0 JUCE_DISPLAY_SPLASH_SCREEN=0)

juce_add_gui_app(A3Desk PRODUCT_NAME "A3 Desk")
target_sources(A3Desk PRIVATE Source/Main.cpp ${A3DESK_SOURCES_ABS})
target_include_directories(A3Desk PRIVATE Source)
target_compile_definitions(A3Desk PRIVATE ${A3DESK_DEFINITIONS}
    JUCE_APPLICATION_NAME_STRING="$<TARGET_PROPERTY:A3Desk,JUCE_PRODUCT_NAME>"
    JUCE_APPLICATION_VERSION_STRING="$<TARGET_PROPERTY:A3Desk,JUCE_VERSION>")
# A rewrite that drops a case must not compile (memory feedback_a-rewrite-drops-a-case).
target_compile_options(A3Desk PRIVATE -Werror=switch)
target_link_libraries(A3Desk
    PRIVATE juce::juce_gui_basics juce::juce_osc juce::juce_cryptography
    PUBLIC juce::juce_recommended_config_flags juce::juce_recommended_lto_flags
           juce::juce_recommended_warning_flags)

option(A3DESK_TESTS "Build the unit tests" OFF)
if(A3DESK_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()
