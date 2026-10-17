# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The desk's code as a source set other apps compile (a3-prodj). Sets four
# variables, no find_package and no target: a consumer compiles the sources
# into its own target with its own JUCE modules, because a static library
# linking JUCE modules would compile the modules twice (a3-motion-ui, 2026-10-03).
get_filename_component(A3DESK_APP_DIR "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)

set(A3DESK_INCLUDE_DIR "${A3DESK_APP_DIR}/Source")

# Everything but Main.cpp.
set(_a3desk_sources
    DeskControls.cpp
    DeskControlsUi.cpp
    DeskIndicatorsUi.cpp
    DeskLook.cpp
    DeskComponent.cpp
    DeskInbox.cpp
    DeskLayout.cpp
    DeskLink.cpp
    DeskMeters.cpp
    EncoderTurns.cpp
    DeskOsc.cpp
    DeskWindow.cpp
    DeskWire.cpp
    DeskState.cpp
    DisplayPaint.cpp
    DisplayPicture.cpp
    LedScale.cpp
    StartupAsk.cpp
    VuInbox.cpp
    shared/MeterBallistics.cpp
    shared/OscSendGuard.cpp
    shared/OscTruth.cpp
    shared/TruthKeeperLink.cpp)
list(TRANSFORM _a3desk_sources PREPEND "${A3DESK_INCLUDE_DIR}/" OUTPUT_VARIABLE A3DESK_LIBRARY_SOURCES)

set(A3DESK_JUCE_MODULES juce::juce_gui_basics juce::juce_osc juce::juce_cryptography)

# What the desk's targets compile with, so a consumer does not copy them.
set(A3DESK_DEFINITIONS JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0 JUCE_DISPLAY_SPLASH_SCREEN=0)
