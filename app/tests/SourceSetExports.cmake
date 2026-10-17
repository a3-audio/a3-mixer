# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Run with `cmake -P`: the source set alone hands another app (a3-prodj)
# everything the desk's targets compile with -- sources, modules and the
# compile definitions -- so nothing is copied into that app's CMakeLists.
include("${CMAKE_CURRENT_LIST_DIR}/../cmake/A3DeskSources.cmake")

foreach(variable A3DESK_INCLUDE_DIR A3DESK_LIBRARY_SOURCES A3DESK_JUCE_MODULES A3DESK_DEFINITIONS)
    if(NOT DEFINED ${variable} OR "${${variable}}" STREQUAL "")
        message(FATAL_ERROR "A3DeskSources.cmake does not set ${variable}")
    endif()
endforeach()

foreach(definition JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0 JUCE_DISPLAY_SPLASH_SCREEN=0)
    if(NOT definition IN_LIST A3DESK_DEFINITIONS)
        message(FATAL_ERROR "A3DESK_DEFINITIONS lacks ${definition}: ${A3DESK_DEFINITIONS}")
    endif()
endforeach()
