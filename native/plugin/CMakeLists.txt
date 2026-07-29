set(sammyblaze_plugin_sources
    source/bridge.cpp
    source/bridge.h
    source/controller.cpp
    source/controller.h
    source/factory.cpp
    source/ids.h
    source/processor.cpp
    source/processor.h
    source/version.h
)

smtg_add_vst3plugin(SammyBlazeVST3
    PACKAGE_NAME "SammyBlaze"
    SOURCES_LIST ${sammyblaze_plugin_sources}
)

target_link_libraries(
    SammyBlazeVST3
    PRIVATE
        sdk
        SammyBlazeAudioCoreEngine
)
if(WIN32)
    target_link_libraries(SammyBlazeVST3 PRIVATE ws2_32)
endif()
target_include_directories(SammyBlazeVST3 PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
target_compile_features(SammyBlazeVST3 PRIVATE cxx_std_20)
smtg_target_configure_version_file(SammyBlazeVST3)

if(MSVC)
    target_compile_options(SammyBlazeVST3 PRIVATE /W4 /permissive-)
endif()

if(BUILD_TESTING)
    add_executable(SammyBlazeDspValidation
        tests/dsp_validation.cpp
    )
    target_link_libraries(
        SammyBlazeDspValidation
        PRIVATE
            SammyBlazeAudioCoreEngine
    )
    target_compile_features(SammyBlazeDspValidation PRIVATE cxx_std_20)
    if(MSVC)
        target_compile_options(SammyBlazeDspValidation PRIVATE /W4 /permissive-)
    endif()
    add_test(
        NAME SammyBlazeDspValidation
        COMMAND SammyBlazeDspValidation
    )
endif()
