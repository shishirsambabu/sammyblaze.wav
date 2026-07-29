cmake_minimum_required(VERSION 3.25)

project(
    SammyBlazeNative
    VERSION 0.3.0
    DESCRIPTION "Native SammyBlaze.wav VST3 performance instrument"
    LANGUAGES CXX
)

set(VST3_SDK_ROOT "" CACHE PATH "Path to a pinned Steinberg VST3 SDK checkout")
if(NOT EXISTS "${VST3_SDK_ROOT}/CMakeLists.txt")
    message(
        FATAL_ERROR
        "Set VST3_SDK_ROOT to Steinberg VST3 SDK 3.8.0 "
        "(for this workstation: D:/SammyBlazeDeps/vst3sdk)"
    )
endif()

set(SMTG_ENABLE_VST3_PLUGIN_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_VSTGUI_SUPPORT OFF CACHE BOOL "" FORCE)
set(SMTG_CREATE_PLUGIN_LINK OFF CACHE BOOL "" FORCE)
# Keep packaging deterministic; validation remains an explicit release-gate command
# in packaging/windows/build-native.ps1 instead of a hidden post-build side effect.
set(SMTG_CREATE_MODULE_INFO OFF CACHE BOOL "" FORCE)
set(SMTG_RUN_VST_VALIDATOR OFF CACHE BOOL "" FORCE)

add_subdirectory("${VST3_SDK_ROOT}" "${CMAKE_BINARY_DIR}/vst3sdk")
add_subdirectory(native/plugin)
