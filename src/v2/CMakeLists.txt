# The version 2 core (docs/semantics_spec_v2.md). Built only with FLUXGRAPH_BUILD_V2, beside the 1.x
# library and sharing nothing with it. Zero dependencies, as the 1.x core has.
add_library(fluxgraph_v2 STATIC
    block_delay.cpp
    block_estimator.cpp
    block_formula.cpp
    block_hold.cpp
    block_integrate.cpp
    block_logic.cpp
    block_model.cpp
    block_pid.cpp
    block_window.cpp
    blocks.cpp
    compiler.cpp
    engine.cpp
    exact.cpp
    exact_step.cpp
    formula.cpp
    model.cpp
    setting.cpp
    state.cpp
)

target_include_directories(fluxgraph_v2 PUBLIC
    $<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}/include>
)

target_compile_features(fluxgraph_v2 PUBLIC cxx_std_20)

# The loaders (fluxgraph/v2/load.hpp), each a library of its own: the core has no dependency.
if(FLUXGRAPH_JSON_ENABLED)
    add_library(fluxgraph_v2_json STATIC load_json.cpp)
    target_link_libraries(fluxgraph_v2_json PUBLIC fluxgraph_v2 PRIVATE nlohmann_json::nlohmann_json)
    target_compile_definitions(fluxgraph_v2_json PUBLIC FLUXGRAPH_V2_JSON)
    list(APPEND FLUXGRAPH_V2_LOADERS fluxgraph_v2_json)
endif()
if(FLUXGRAPH_YAML_ENABLED)
    add_library(fluxgraph_v2_yaml STATIC load_yaml.cpp)
    target_link_libraries(fluxgraph_v2_yaml PUBLIC fluxgraph_v2 PRIVATE yaml-cpp::yaml-cpp)
    target_compile_definitions(fluxgraph_v2_yaml PUBLIC FLUXGRAPH_V2_YAML)
    list(APPEND FLUXGRAPH_V2_LOADERS fluxgraph_v2_yaml)
endif()
set(FLUXGRAPH_V2_LOADERS "${FLUXGRAPH_V2_LOADERS}" PARENT_SCOPE)

# The warnings the 1.x target is built with.
foreach(target fluxgraph_v2 ${FLUXGRAPH_V2_LOADERS})
if(MSVC)
    target_compile_options(${target} PRIVATE /W4 /WX)
else()
    # -Wshadow: MSVC's /W4 refuses a local that hides a member (C4458), and a build here should say so first.
    # -Wconversion: likewise its C4244, though not where the narrowing is inside a standard header.
    target_compile_options(${target} PRIVATE -Wall -Wextra -Wshadow -Wconversion -Werror -pedantic)
endif()
endforeach()
