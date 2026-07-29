cmake_minimum_required(VERSION 3.25)

project(
    SammyBlazeNative
    VERSION 0.4.0
    DESCRIPTION "Native SammyBlaze.wav VST3 performance instrument"
    LANGUAGES CXX
)

include(CTest)

# The public Windows payload must not require a separately installed Visual C++
# redistributable. The C ABI crosses only POD values and buffers, so keeping one
# static MSVC runtime per native module is safe and makes clean-machine behavior
# explicit. A validation-tool build may opt out because those tools are not
# distributed. Set this before creating SDK or product targets.
option(
    SAMMYBLAZE_STATIC_MSVC_RUNTIME
    "Statically link the MSVC runtime into distributed Windows modules"
    ON
)
if(MSVC AND SAMMYBLAZE_STATIC_MSVC_RUNTIME)
    set(
        CMAKE_MSVC_RUNTIME_LIBRARY
        "MultiThreaded$<$<CONFIG:Debug>:Debug>"
    )
endif()

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
set(
    SMTG_USE_STATIC_CRT
    ${SAMMYBLAZE_STATIC_MSVC_RUNTIME}
    CACHE BOOL
    ""
    FORCE
)
# Keep packaging deterministic; validation remains an explicit release-gate command
# in packaging/windows/build-native.ps1 instead of a hidden post-build side effect.
set(SMTG_CREATE_MODULE_INFO OFF CACHE BOOL "" FORCE)
set(SMTG_RUN_VST_VALIDATOR OFF CACHE BOOL "" FORCE)

add_subdirectory("${VST3_SDK_ROOT}" "${CMAKE_BINARY_DIR}/vst3sdk")
add_subdirectory(native/audio_core)
add_subdirectory(native/plugin)
