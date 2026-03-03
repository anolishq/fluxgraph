# Tests use vcpkg-provided GoogleTest (manifest feature: tests)
find_package(GTest CONFIG REQUIRED)

# Test executable
add_executable(fluxgraph_tests
    unit/signal_store_test.cpp
    unit/namespace_test.cpp
    unit/command_test.cpp
    unit/transform_linear_test.cpp
    unit/transform_lag_test.cpp
    unit/transform_delay_test.cpp
    unit/transform_noise_test.cpp
    unit/transform_saturation_test.cpp
    unit/transform_deadband_test.cpp
    unit/transform_rate_limiter_test.cpp
    unit/transform_moving_average_test.cpp
    unit/thermal_mass_test.cpp
    unit/compiler_test.cpp
    unit/engine_test.cpp
    analytical/first_order_lag_analytical_test.cpp
    analytical/thermal_mass_analytical_test.cpp
    analytical/delay_analytical_test.cpp
    analytical/transform_analytical_test.cpp
)

target_link_libraries(fluxgraph_tests
    PRIVATE fluxgraph
    PRIVATE GTest::gtest_main
)

target_compile_definitions(fluxgraph_tests PRIVATE
    FLUXGRAPH_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
)

if(FLUXGRAPH_BUILD_DIAGRAM_TOOL)
    target_sources(fluxgraph_tests PRIVATE
        unit/viz_format_test.cpp
        unit/viz_graphviz_renderer_test.cpp
        unit/viz_dot_emitter_test.cpp
        unit/viz_dot_golden_test.cpp
    )
    target_link_libraries(fluxgraph_tests PRIVATE fluxgraph_viz_core)
endif()

# Discover tests
include(GoogleTest)
gtest_discover_tests(fluxgraph_tests
    DISCOVERY_MODE POST_BUILD
    DISCOVERY_TIMEOUT 60
)

# Optional loader tests (separate executables for conditional compilation)
if(FLUXGRAPH_JSON_ENABLED)
    add_executable(json_loader_test unit/json_loader_test.cpp)
    target_link_libraries(json_loader_test
        PRIVATE fluxgraph
        PRIVATE GTest::gtest_main
    )
    gtest_discover_tests(json_loader_test
        DISCOVERY_MODE POST_BUILD
        DISCOVERY_TIMEOUT 60
    )
endif()

if(FLUXGRAPH_YAML_ENABLED)
    add_executable(yaml_loader_test unit/yaml_loader_test.cpp)
    target_link_libraries(yaml_loader_test
        PRIVATE fluxgraph
        PRIVATE GTest::gtest_main
    )
    gtest_discover_tests(yaml_loader_test
        DISCOVERY_MODE POST_BUILD
        DISCOVERY_TIMEOUT 60
    )
endif()

if(FLUXGRAPH_BUILD_DIAGRAM_TOOL AND FLUXGRAPH_JSON_ENABLED)
    add_test(
        NAME integration.diagram_cli_json_dot
        COMMAND ${CMAKE_COMMAND}
            -DCLI=$<TARGET_FILE:fluxgraph_diagram>
            -DINPUT=${CMAKE_SOURCE_DIR}/examples/03_json_graph/graph.json
            -DOUTPUT_DIR=${CMAKE_BINARY_DIR}/diagram-tests
            -P ${CMAKE_CURRENT_SOURCE_DIR}/integration/diagram_cli_e2e.cmake
    )
endif()

# -----------------------------------------------------------------------------
# Python Integration Tests (pytest)
# -----------------------------------------------------------------------------

if(FLUXGRAPH_BUILD_SERVER)
    find_package(Python3 COMPONENTS Interpreter REQUIRED)

    # Register pytest as a CTest test
    # This allows 'ctest' to run both C++ unit tests and Python integration tests
    add_test(
        NAME integration.pytest
        COMMAND ${Python3_EXECUTABLE} -m pytest
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    )

    # Pass build artifacts to pytest via environment variables
    set_tests_properties(integration.pytest PROPERTIES
        ENVIRONMENT "FLUXGRAPH_SERVER_EXE=$<TARGET_FILE:fluxgraph-server>;FLUXGRAPH_PROTO_PYTHON_DIR=${CMAKE_BINARY_DIR}/python"
    )
endif()

# Benchmark tests
add_subdirectory(benchmarks)
add_subdirectory(validation)

# Add test command
add_custom_target(check
    COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure
    DEPENDS fluxgraph_tests
)
