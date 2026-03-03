cmake_minimum_required(VERSION 3.20)

# Build options (set before project() so vcpkg manifest features can be mapped)
option(FLUXGRAPH_BUILD_TESTS "Build unit tests" ON)
option(FLUXGRAPH_BUILD_EXAMPLES "Build examples" ON)
option(FLUXGRAPH_BUILD_SERVER "Build gRPC server" OFF)
option(FLUXGRAPH_BUILD_DIAGRAM_TOOL "Build diagram generation tooling" OFF)
option(FLUXGRAPH_JSON_ENABLED "Enable JSON graph loading (requires nlohmann/json)" OFF)
option(FLUXGRAPH_YAML_ENABLED "Enable YAML graph loading (requires yaml-cpp)" OFF)

# Map CMake options -> vcpkg manifest features for deterministic dependency resolution.
if(FLUXGRAPH_BUILD_TESTS)
    list(APPEND VCPKG_MANIFEST_FEATURES "tests")
endif()

if(FLUXGRAPH_BUILD_SERVER)
    list(APPEND VCPKG_MANIFEST_FEATURES "server")
endif()

if(FLUXGRAPH_JSON_ENABLED)
    list(APPEND VCPKG_MANIFEST_FEATURES "json")
endif()

if(FLUXGRAPH_YAML_ENABLED)
    list(APPEND VCPKG_MANIFEST_FEATURES "yaml")
endif()

project(fluxgraph VERSION 0.1.1 LANGUAGES CXX)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

# C++17 required
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Export compile commands for IDE support
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Core library sources
set(FLUXGRAPH_SOURCES
    src/core/signal_store.cpp
    src/core/namespace.cpp
    src/core/units.cpp
    src/model/thermal_mass.cpp
    src/graph/compiler.cpp
    src/engine.cpp
)

# Conditionally add loader sources and resolve dependencies from vcpkg
if(FLUXGRAPH_JSON_ENABLED)
    list(APPEND FLUXGRAPH_SOURCES src/loaders/json_loader.cpp)
    find_package(nlohmann_json CONFIG REQUIRED)
endif()

if(FLUXGRAPH_YAML_ENABLED)
    list(APPEND FLUXGRAPH_SOURCES src/loaders/yaml_loader.cpp)
    find_package(yaml-cpp CONFIG REQUIRED)
endif()

# Create static library
add_library(fluxgraph STATIC ${FLUXGRAPH_SOURCES})

# Public include directory
target_include_directories(fluxgraph PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

# Compiler warnings
if(MSVC)
    target_compile_options(fluxgraph PRIVATE /W4 /WX)
else()
    target_compile_options(fluxgraph PRIVATE -Wall -Wextra -Werror -pedantic)
endif()

# Link optional dependencies
if(FLUXGRAPH_JSON_ENABLED)
    target_link_libraries(fluxgraph PUBLIC nlohmann_json::nlohmann_json)
    target_compile_definitions(fluxgraph PUBLIC FLUXGRAPH_JSON_ENABLED)
endif()

if(FLUXGRAPH_YAML_ENABLED)
    target_link_libraries(fluxgraph PUBLIC yaml-cpp::yaml-cpp)
    target_compile_definitions(fluxgraph PUBLIC FLUXGRAPH_YAML_ENABLED)
endif()

# Optional diagram tooling
if(FLUXGRAPH_BUILD_DIAGRAM_TOOL)
    add_subdirectory(tools)
endif()

# Tests
if(FLUXGRAPH_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

# Examples
if(FLUXGRAPH_BUILD_EXAMPLES)
    add_subdirectory(examples)
endif()

# gRPC Server
if(FLUXGRAPH_BUILD_SERVER)
    add_subdirectory(server)
endif()

# Install/export package configuration
install(TARGETS fluxgraph
    EXPORT fluxgraphTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)

if(FLUXGRAPH_BUILD_DIAGRAM_TOOL)
    install(DIRECTORY include/fluxgraph
        DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
    )
else()
    install(DIRECTORY include/fluxgraph
        DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
        PATTERN "viz" EXCLUDE
    )
endif()

install(EXPORT fluxgraphTargets
    FILE fluxgraphTargets.cmake
    NAMESPACE fluxgraph::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/fluxgraph
)

configure_package_config_file(
    ${CMAKE_CURRENT_SOURCE_DIR}/cmake/fluxgraphConfig.cmake.in
    ${CMAKE_CURRENT_BINARY_DIR}/fluxgraphConfig.cmake
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/fluxgraph
)

write_basic_package_version_file(
    ${CMAKE_CURRENT_BINARY_DIR}/fluxgraphConfigVersion.cmake
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)

install(FILES
    ${CMAKE_CURRENT_BINARY_DIR}/fluxgraphConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/fluxgraphConfigVersion.cmake
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/fluxgraph
)
