cmake_minimum_required(VERSION 3.26)

if(NOT DEFINED CMAKE_CUDA_COMPILER)
    if(DEFINED ENV{CUDA_PATH} AND EXISTS "$ENV{CUDA_PATH}/bin/nvcc.exe")
        set(CMAKE_CUDA_COMPILER "$ENV{CUDA_PATH}/bin/nvcc.exe" CACHE FILEPATH "CUDA compiler" FORCE)
        set(CUDAToolkit_ROOT "$ENV{CUDA_PATH}" CACHE PATH "CUDA toolkit root" FORCE)
    elseif(CMAKE_HOST_WIN32)
        file(GLOB _SPOOLSTREAM_CUDA_ROOTS
            LIST_DIRECTORIES true
            "C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v*"
        )
        list(SORT _SPOOLSTREAM_CUDA_ROOTS COMPARE NATURAL ORDER DESCENDING)
        foreach(_SPOOLSTREAM_CUDA_ROOT IN LISTS _SPOOLSTREAM_CUDA_ROOTS)
            if(EXISTS "${_SPOOLSTREAM_CUDA_ROOT}/bin/nvcc.exe")
                set(CMAKE_CUDA_COMPILER "${_SPOOLSTREAM_CUDA_ROOT}/bin/nvcc.exe" CACHE FILEPATH "CUDA compiler" FORCE)
                set(CUDAToolkit_ROOT "${_SPOOLSTREAM_CUDA_ROOT}" CACHE PATH "CUDA toolkit root" FORCE)
                break()
            endif()
        endforeach()
    endif()
endif()

project(RIFT LANGUAGES CXX CUDA)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_STANDARD_REQUIRED ON)
set(CMAKE_CUDA_EXTENSIONS OFF)

if(MSVC)
    # Every native target uses exceptions for defensive error propagation.
    add_compile_options($<$<COMPILE_LANGUAGE:CXX>:/EHsc>)
endif()

if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES)
    set(CMAKE_CUDA_ARCHITECTURES native)
endif()

add_library(spoolstream_core STATIC
    native/src/parser.cpp
    native/src/model.cpp
    native/src/quantized_adapter.cpp
    native/src/execution_policy.cpp
    native/src/streaming_store.cpp
    native/src/layer_scheduler.cpp
    native/src/survival/memory_manager.cu
    native/src/survival/kernels.cu
    native/src/survival/pipeline.cu
    native/src/survival/speculative_engine.cu
    native/src/survival/kv_cache.cu
    native/src/survival/transformer_executor.cu
)

find_package(CUDAToolkit REQUIRED)
find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)

target_include_directories(spoolstream_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/native/include
)

target_link_libraries(spoolstream_core
    PUBLIC
        CUDA::cudart
)

set_target_properties(spoolstream_core PROPERTIES
    CUDA_SEPARABLE_COMPILATION OFF
    CUDA_RESOLVE_DEVICE_SYMBOLS OFF
    POSITION_INDEPENDENT_CODE ON
)

if(MSVC)
    target_compile_options(spoolstream_core PRIVATE
        $<$<COMPILE_LANGUAGE:CXX>:/W4 /permissive->
        $<$<COMPILE_LANGUAGE:CUDA>:--expt-relaxed-constexpr>
    )
else()
    target_compile_options(spoolstream_core PRIVATE
        $<$<COMPILE_LANGUAGE:CXX>:-Wall -Wextra -Wpedantic>
        $<$<COMPILE_LANGUAGE:CUDA>:--expt-relaxed-constexpr>
    )
endif()

Python_add_library(spoolstream_python MODULE
    native/src/bindings.cpp
    WITH_SOABI
)

target_include_directories(spoolstream_python
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/native/include
)

target_link_libraries(spoolstream_python
    PRIVATE
        spoolstream_core
        CUDA::cudart
)

set_target_properties(spoolstream_python PROPERTIES
    OUTPUT_NAME "_core"
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
)

install(TARGETS spoolstream_python
    LIBRARY DESTINATION spoolstream
    RUNTIME DESTINATION spoolstream
)

install(DIRECTORY python/spoolstream python/rift
    DESTINATION .
    FILES_MATCHING
    PATTERN "*.py"
    PATTERN "__pycache__" EXCLUDE
    PATTERN "*.pyc" EXCLUDE
)

install(DIRECTORY docs
    DESTINATION rift
)

install(FILES README.md CHANGELOG.md LICENSE
    DESTINATION rift
)

install(DIRECTORY examples/
    DESTINATION rift/examples
)

enable_testing()

add_executable(spoolstream_parser_tests
    tests/native/parser_tests.cpp
)

target_link_libraries(spoolstream_parser_tests PRIVATE spoolstream_core)

add_test(NAME spoolstream_parser_tests COMMAND spoolstream_parser_tests)

add_executable(spoolstream_memory_manager_tests
    tests/native/memory_manager_tests.cpp
)

target_link_libraries(spoolstream_memory_manager_tests PRIVATE spoolstream_core)

add_test(NAME spoolstream_memory_manager_tests COMMAND spoolstream_memory_manager_tests)

add_executable(spoolstream_kernel_tests
    tests/native/kernel_tests.cpp
)

target_link_libraries(spoolstream_kernel_tests PRIVATE spoolstream_core)

add_test(NAME spoolstream_kernel_tests COMMAND spoolstream_kernel_tests)

add_executable(spoolstream_pipeline_tests
    tests/native/pipeline_tests.cpp
)

target_link_libraries(spoolstream_pipeline_tests PRIVATE spoolstream_core)

add_test(NAME spoolstream_pipeline_tests COMMAND spoolstream_pipeline_tests)

add_executable(spoolstream_speculative_tests
    tests/native/speculative_engine_tests.cpp
)

target_link_libraries(spoolstream_speculative_tests PRIVATE spoolstream_core)

add_test(NAME spoolstream_speculative_tests COMMAND spoolstream_speculative_tests)

add_executable(spoolstream_kv_cache_tests
    tests/native/kv_cache_tests.cpp
)

target_link_libraries(spoolstream_kv_cache_tests PRIVATE spoolstream_core)

add_test(NAME spoolstream_kv_cache_tests COMMAND spoolstream_kv_cache_tests)

add_executable(spoolstream_model_tests
    tests/native/model_tests.cpp
)

target_link_libraries(spoolstream_model_tests PRIVATE spoolstream_core)

add_test(NAME spoolstream_model_tests COMMAND spoolstream_model_tests)

add_executable(spoolstream_layer_scheduler_tests
    tests/native/layer_scheduler_tests.cpp
)

target_link_libraries(spoolstream_layer_scheduler_tests PRIVATE spoolstream_core)

add_test(NAME spoolstream_layer_scheduler_tests COMMAND spoolstream_layer_scheduler_tests)

add_executable(spoolstream_transformer_executor_tests
    tests/native/transformer_executor_tests.cpp
)

target_link_libraries(spoolstream_transformer_executor_tests PRIVATE spoolstream_core)

add_test(NAME spoolstream_transformer_executor_tests COMMAND spoolstream_transformer_executor_tests)

add_executable(spoolstream_execution_policy_tests
    tests/native/execution_policy_tests.cpp
)

target_link_libraries(spoolstream_execution_policy_tests PRIVATE spoolstream_core)

add_test(NAME spoolstream_execution_policy_tests COMMAND spoolstream_execution_policy_tests)

add_executable(spoolstream_quantized_adapter_tests
    tests/native/quantized_adapter_tests.cpp
)

target_link_libraries(spoolstream_quantized_adapter_tests PRIVATE spoolstream_core)

add_test(NAME spoolstream_quantized_adapter_tests COMMAND spoolstream_quantized_adapter_tests)

add_executable(spoolstream_real_gptq_smoke
    tests/native/real_gptq_smoke.cpp
)

target_link_libraries(spoolstream_real_gptq_smoke PRIVATE spoolstream_core)

add_test(NAME spoolstream_dashboard_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/dashboard_tests.py
)

add_test(NAME spoolstream_rift_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/rift_tests.py
)

add_test(NAME spoolstream_server_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/server_tests.py
)

add_test(NAME spoolstream_hf_hub_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/hf_hub_tests.py
)

add_test(NAME spoolstream_recommend_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/recommend_tests.py
)

add_test(NAME spoolstream_orchestrator_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/orchestrator_tests.py
)

add_test(NAME spoolstream_adapter_host_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/adapter_host_tests.py
)

add_test(NAME spoolstream_node_agent_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/node_agent_tests.py
)

add_test(NAME spoolstream_provider_adapter_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/provider_adapter_tests.py
)

add_test(NAME spoolstream_artifact_adapter_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/artifact_adapter_tests.py
)

add_test(NAME spoolstream_gateway_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/gateway_tests.py
)

add_test(NAME spoolstream_cluster_control_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/cluster_control_tests.py
)

add_test(NAME rift_control_plane_roadmap_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/control_plane_roadmap_tests.py
)

add_test(NAME rift_mesh_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/mesh_tests.py
)

add_test(NAME rift_container_manifest_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/container_manifest_tests.py
)

add_test(NAME rift_android_manifest_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/android_manifest_tests.py
)

add_test(NAME rift_state_store_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/state_store_tests.py
)
add_test(NAME rift_cli_surface_tests
    COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/python/cli_surface_tests.py
)
