set(sammyblaze_audio_core_sources
    source/presets.cpp
    source/synth_engine.cpp
    include/sammyblaze/audio_core/dsp.h
    include/sammyblaze/audio_core/presets.h
    include/sammyblaze/audio_core/synth_engine.h
)

add_library(SammyBlazeAudioCoreEngine STATIC
    ${sammyblaze_audio_core_sources}
)
target_include_directories(
    SammyBlazeAudioCoreEngine
    PUBLIC
        "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
target_compile_features(SammyBlazeAudioCoreEngine PUBLIC cxx_std_20)
set_target_properties(
    SammyBlazeAudioCoreEngine
    PROPERTIES
        POSITION_INDEPENDENT_CODE ON
)

add_library(SammyBlazeAudioCore SHARED
    source/audio_core_c.cpp
    include/sammyblaze/audio_core/audio_core_c.h
)
target_link_libraries(
    SammyBlazeAudioCore
    PRIVATE
        SammyBlazeAudioCoreEngine
)
target_include_directories(
    SammyBlazeAudioCore
    PUBLIC
        "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
target_compile_features(SammyBlazeAudioCore PRIVATE cxx_std_20)
target_compile_definitions(SammyBlazeAudioCore PRIVATE SBW_AUDIO_CORE_BUILD)
set_target_properties(
    SammyBlazeAudioCore
    PROPERTIES
        OUTPUT_NAME "SammyBlazeAudioCore"
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
        WINDOWS_EXPORT_ALL_SYMBOLS OFF
)

if(MSVC)
    target_compile_options(
        SammyBlazeAudioCoreEngine
        PRIVATE
            /W4
            /permissive-
    )
    target_compile_options(
        SammyBlazeAudioCore
        PRIVATE
            /W4
            /permissive-
    )
endif()

if(BUILD_TESTING)
    add_executable(
        SammyBlazeAudioCoreValidation
        tests/audio_core_validation.cpp
    )
    target_link_libraries(
        SammyBlazeAudioCoreValidation
        PRIVATE
            SammyBlazeAudioCoreEngine
    )
    target_compile_features(
        SammyBlazeAudioCoreValidation
        PRIVATE
            cxx_std_20
    )

    add_executable(
        SammyBlazeAudioCoreAbiValidation
        tests/audio_core_abi_validation.cpp
    )
    target_link_libraries(
        SammyBlazeAudioCoreAbiValidation
        PRIVATE
            SammyBlazeAudioCore
    )
    target_compile_features(
        SammyBlazeAudioCoreAbiValidation
        PRIVATE
            cxx_std_20
    )

    add_executable(
        SammyBlazeAudioCoreBenchmark
        tests/audio_core_benchmark.cpp
    )
    target_link_libraries(
        SammyBlazeAudioCoreBenchmark
        PRIVATE
            SammyBlazeAudioCoreEngine
    )
    target_compile_features(
        SammyBlazeAudioCoreBenchmark
        PRIVATE
            cxx_std_20
    )

    if(MSVC)
        foreach(
            target
            SammyBlazeAudioCoreValidation
            SammyBlazeAudioCoreAbiValidation
            SammyBlazeAudioCoreBenchmark
        )
            target_compile_options(${target} PRIVATE /W4 /permissive-)
        endforeach()
    endif()

    add_test(
        NAME SammyBlazeAudioCoreValidation
        COMMAND SammyBlazeAudioCoreValidation
    )
    add_test(
        NAME SammyBlazeAudioCoreAbiValidation
        COMMAND SammyBlazeAudioCoreAbiValidation
    )

    if(WIN32)
        find_program(
            SBW_POWERSHELL_EXECUTABLE
            NAMES powershell.exe
            REQUIRED
        )
        find_program(
            SBW_PYTHON_EXECUTABLE
            NAMES python.exe
            PATHS "D:/Python312"
            NO_DEFAULT_PATH
        )
        if(SBW_PYTHON_EXECUTABLE)
            add_test(
                NAME SammyBlazeAudioCoreAbiRuntimeValidation
                COMMAND
                    "${SBW_POWERSHELL_EXECUTABLE}"
                    -NoProfile
                    -ExecutionPolicy Bypass
                    -File
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/run_abi_validation.ps1"
                    -DllPath
                    "$<TARGET_FILE:SammyBlazeAudioCore>"
                    -Python
                    "${SBW_PYTHON_EXECUTABLE}"
            )
            set_tests_properties(
                SammyBlazeAudioCoreAbiRuntimeValidation
                PROPERTIES
                    LABELS "abi;benchmark;runtime"
                    TIMEOUT 120
            )
        endif()
    endif()
endif()
